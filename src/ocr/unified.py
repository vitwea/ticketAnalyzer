from __future__ import annotations

import json
from google import genai
from google.genai import types
from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)

client = genai.Client(api_key=settings.anthropic_api_key)


def extract_ticket_data(file_bytes: bytes, mime_type: str) -> dict:
    """
    Extract structured ticket data from a PDF or image using Gemini 2.5 Flash.
    Returns a dict with supermarket, date, products, totals, etc.
    """

    logger.info(f"Sending {mime_type} ({len(file_bytes)} bytes) to Gemini 2.5 Flash OCR...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            types.Part.from_text(text="""
Eres un sistema experto en lectura de tickets de supermercado.

Tu tarea es analizar el texto del ticket y devolver un JSON ESTRICTO con esta estructura:

{
  "supermarket": "Mercadona",
  "date": "2026-06-15",
  "time": "12:33",
  "store": "C/Tenor Gayarre, 4 (50010, Zaragoza)",
  "source": "Email",
  "total": 23.45,
  "products": [
    {
      "name": "Tomate pera",
      "original_name": "PLT TOM 1KG",
      "category": "Verduras",
      "brand": null,
      "quantity": 1.25,
      "unit": "kg",
      "original_unit_price": 1.91,
      "discount": 0,
      "final_unit_price": 1.91,
      "line_total": 2.39
    }
  ]
}

REGLAS IMPORTANTES:

1) CATEGORÍAS FIJAS (elige SOLO una):
- Lácteos
- Carnes
- Pescados
- Frutas
- Verduras
- Panadería
- Bebidas
- Droguería
- Higiene
- Congelados
- Snacks
- Huevos
- Cereales y pasta
- Salsas y conservas
- Otros

2) MARCA (BRAND):
El campo "brand" debe reflejar la marca real del producto, esté impresa literalmente en el ticket o no. Sigue este orden de decisión:

   CASO A — Marca de fabricante visible:
   - Si el ticket menciona una marca comercial reconocible (ej. "Coca-Cola", "Danone", "Colgate", "Pascual", "Nestlé") → úsala en "brand" y elimínala de "name".

   CASO B — Sin marca de fabricante visible, pero es un producto ENVASADO/MANUFACTURADO:
   - Si no hay marca de fabricante en el ticket pero el producto es de los que el supermercado vende bajo su propia marca blanca, asigna la marca propia de ESE supermercado. Usa esta referencia (España):
       - Mercadona → "Hacendado" (alimentación), "Deliplus" (higiene/cosmética), "Bosque Verde" (limpieza/droguería ecológica)
       - Carrefour → "Carrefour"
       - Alcampo → "Auchan"
       - Eroski → "Eroski"
       - Dia → "Dia"
       - Lidl → usa la sub-marca propia si la reconoces (ej. "Milbona" lácteos, "Pilos" detergente, "Vitasia" comida asiática); si no la identificas con seguridad, usa "Lidl"
       - Aldi → usa la sub-marca propia si la reconoces; si no, usa "Aldi"
       - Consum, Caprabo, Ahorramas, Condis, Gadis, Froiz u otros no listados → usa el propio nombre del supermercado como marca (ej. "Condis") SOLO si el producto es claramente envasado y de marca blanca.
   - Si el "supermarket" detectado no permite determinar con confianza una marca blanca, usa null en vez de forzarla.

   CASO C — Producto fresco a granel SIN marca (no aplica marca blanca):
   - Frutas, verduras, carne, pescado, panadería o charcutería vendidos sueltos/a granel/por peso NO suelen llevar marca → usa "brand": null, salvo que el ticket indique explícitamente una marca (ej. "Jamón Serrano Navidul", "Pollo Coren").
   - No asignes la marca blanca del supermercado a este tipo de productos frescos: la regla del CASO B es solo para envasados/manufacturados.

   En caso de duda razonable entre marca blanca o ninguna marca, prioriza "brand": null antes que inventar.

3) NOMBRES DE PRODUCTO:
- COMPLETA nombres truncados o abreviados usando conocimiento general de productos de supermercado.
- El campo "name" debe contener el nombre normalizado, sin cantidades, unidades ni marca (excepto para packs).
- El campo "original_name" debe contener el nombre EXACTO tal como aparece en el ticket, sin modificar.
- Si al extraer la marca (fabricante o blanca) el nombre resultante queda incompleto, ambiguo o poco intuitivo, COMPLÉTALO para que describa claramente qué es el producto, sin volver a incluir la marca dentro de "name".
- Ejemplos:
    - original_name: "PLT TOM 1KG" → name: "Tomate pera", brand: null
    - original_name: "MANZ ROJA 1KG" → name: "Manzana roja", brand: null
    - original_name: "HUEV L 12UD" → name: "Huevos tamaño L (12 unidades)", brand: null
    - original_name: "YOGUR HACENDADO NAT" → name: "Yogur natural", brand: "Hacendado"
    - original_name: "COCA COLA 1.5L" → name: "Refresco de cola 1.5L", brand: "Coca-Cola"
    - original_name: "COLGATE ANTICARIES" → name: "Pasta de dientes anticaries", brand: "Colgate"
    - original_name: "YOGUR NAT PACK4" (Mercadona, sin marca de fabricante) → name: "Yogur natural (pack de 4)", brand: "Hacendado"

4) TIENDA (STORE):
- El campo "store" debe representar la dirección física en este formato EXACTO:
    "DIRECCIÓN (CODIGO_POSTAL, CIUDAD)"
  Ejemplo: "C/Tenor Gayarre, 4 (50010, Zaragoza)"
- DIRECCIÓN: calle y número tal como aparecen en el ticket.
- CODIGO_POSTAL: código postal (normalmente 5 cifras en España).
- CIUDAD: nombre de la ciudad o localidad.
- Si NO puedes identificar dirección + código postal + ciudad de forma fiable, usa null en "store". No inventes ni aproximes una dirección.

5) PRECIOS Y CANTIDADES:
- original_unit_price: precio por unidad ANTES de descuentos.
- discount: cantidad descontada (0 si no hay descuento).
- final_unit_price: precio final por unidad DESPUÉS de descuentos (original_unit_price - discount).
- line_total: precio total de la línea (quantity × final_unit_price).
- quantity: cantidad comprada.
- unit: unidad de medida (kg, unidad, litro, etc.).

6) FUENTE (SOURCE):
- El campo "source" indica el origen del ticket. Si no se especifica lo contrario, usa "Email".

7) NO INVENTAR:
- No inventes productos que no aparezcan en el ticket.
- No inventes precios, cantidades ni direcciones.
- La asignación de marca blanca del CASO B es una inferencia permitida (no es "inventar"), pero solo cuando el producto es claramente envasado/manufacturado y el supermercado es conocido.

8) SI FALTA INFORMACIÓN:
- Si no puedes determinar un dato, usa null.
- Si no puedes determinar la categoría, usa "Otros".
- Los campos "time" y "brand" son opcionales, pueden ser null.

9) JSON:
- Devuelve SIEMPRE un JSON válido, sin texto adicional.
- No incluyas explicaciones.
"""),
        ]
    )

    raw = response.text.strip()

    # Limpiar markdown por si Gemini devuelve ```json ... ```
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        logger.info("Gemini 2.5 Flash OCR extraction successful.")
        return data
    except Exception as e:
        logger.error(f"Error parsing Gemini JSON: {e}")
        logger.error(f"Raw response: {raw}")
        raise