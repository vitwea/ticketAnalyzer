from __future__ import annotations

import json
from google import genai
from google.genai import types
from src.config.settings import settings
from src.config.logger import get_logger
from src.ocr.examples import build_examples_block

logger = get_logger(__name__)

client = genai.Client(api_key=settings.anthropic_api_key)

_PROMPT = _PROMPT = """
Eres un sistema experto en lectura de tickets de supermercado españoles.
Devuelve SIEMPRE un JSON ESTRICTO, sin texto adicional ni bloques markdown.

ESTRUCTURA DE SALIDA
{
  "supermarket": "Mercadona",
  "date": "2026-06-15",
  "time": "14:33",
  "store": "Avda. Francisco de Goya, 61 (50005, Zaragoza)",
  "source": "Email",
  "total": 28.63,
  "products": [
    {
      "name": "Tomate pera",
      "original_name": "PLT TOM 1KG",
      "category": "Verduras y hortalizas",
      "brand": null,
      "quantity": 1.25,
      "unit": "kg",
      "original_unit_price": 1.91,
      "discount": 0.0,
      "final_unit_price": 1.91,
      "line_total": 2.39
    }
  ]
}

═══════════════════════════════════════════════════════════
1. SUPERMARKET — nombre comercial, nunca razón social
═══════════════════════════════════════════════════════════
Conocidos (normaliza exacto, ignorando forma jurídica):
  Mercadona · Lidl · Dia · Carrefour · Alcampo · Eroski · Aldi · Consum
  Caprabo · Ahorramas · Condis · Gadis · El Corte Inglés (incluye Supercor)
  Simply · Supersol (incluye Coaliment)

Desconocidos: elimina forma jurídica (S.A./S.L./S.A.U./S.COOP/C.B.) y NIF/CIF,
usa formato título. Ej: "SUPERMERCADOS PACO GARCIA, S.L. B12345678" → "Supermercados Paco Garcia"

Franquicias: si la cabecera muestra la razón social del franquiciado pero el
ticket indica la cadena real ("Productos vendidos por X", "Total venta X",
"REF.X:", logo visible) → usa esa cadena.

═══════════════════════════════════════════════════════════
2. STORE — formato "Dirección (CP, Ciudad)"
═══════════════════════════════════════════════════════════
Prioridad de fuente: 1) "Compra realizada en" / pie del ticket digital
  2) cabecera  3) datos de operación al pie.

Normaliza: MAYÚSCULAS → título. Expande CL→C/, AVDA→Avda., PZA→Pza., URB→Urb.
Si hay intersección ("con C/...", "esquina..."), omítela.
Si dirección y CP/ciudad están en zonas distintas del ticket, combínalas.
Si no hay seguridad de dirección+CP+ciudad → null. No inventes.

═══════════════════════════════════════════════════════════
3. DESCUENTOS — líneas justo después de un producto
═══════════════════════════════════════════════════════════
Patrones de línea de descuento (NUNCA es un producto):
  "PROMO", "Descuento", "Desc.", "DTO.", "Oferta" + valor negativo;
  cualquier valor negativo indentado tras un producto;
  fidelidad: "PROMO LIDL PLUS", "Club Carrefour", "Descuento Dia Card", etc.

Reglas:
  - No crear producto con ese nombre.
  - El valor absoluto es "discount" del producto inmediatamente anterior.
  - Varias líneas de descuento consecutivas → súmalas.
  - final_unit_price = original_unit_price − discount (unidades)
                      = (line_total − discount) / quantity (peso variable)
  - Ignora líneas-resumen al pie ("Total oferta Lidl Plus", "Ahorro total")
    y cupones para compras futuras.

Ejemplo: "BANANA 0,772kg x 1,49€/kg  1,15" + "PROMO LIDL PLUS  -0,39"
  → quantity=0.772, unit=kg, original_unit_price=1.49, discount=0.39,
    final_unit_price=1.10, line_total=0.85

═══════════════════════════════════════════════════════════
4. PESO VARIABLE
═══════════════════════════════════════════════════════════
Formatos: "kg / €kg / total" en 1 o 2 líneas, en cualquier orden.
  quantity = peso en kg · unit = "kg" · original_unit_price = precio/kg
  line_total = importe final de la línea
Con descuento: discount = importe descontado en la línea (no por kg);
  final_unit_price = (line_total − discount) / quantity, redondeado a 2 decimales.
Sin descuento: discount = 0.0, final_unit_price = original_unit_price.

═══════════════════════════════════════════════════════════
5. MÚLTIPLES UNIDADES
═══════════════════════════════════════════════════════════
"2 ARROZ CAMPESTRE 2,00 4,00" → quantity=2, original_unit_price=2.00 (por unidad), line_total=4.00
"3 x 1,50" → quantity=3, original_unit_price=1.50, line_total=4.50
original_unit_price es SIEMPRE por unidad, nunca el total.

═══════════════════════════════════════════════════════════
6. CATEGORÍAS — elige EXACTAMENTE UNA
═══════════════════════════════════════════════════════════
Lácteos
  Leche, yogur, queso, mantequilla, nata, kéfir, postres lácteos.
  Bebidas vegetales (avena/soja/almendra) → Bebidas, no Lácteos.

Carnes y embutidos
  Carne fresca/envasada, embutidos (jamón, chorizo, bacon, fuet),
  precocinados cárnicos (nuggets, delicias de pollo, rebozados).

Pescados y mariscos
  Fresco/envasado, marisco, conservas de pescado (atún, sardinas),
  ahumados, surimi, boquerones en vinagre.

Frutas
  Fruta fresca o en bolsa.

Verduras y hortalizas
  Verdura/hortaliza fresca o envasada, ensaladas en bolsa, ajo fresco.

Pan
  Pan fresco o envasado: barra, molde, integral, pita, picos, regañás,
  base de pizza, tortitas de maíz/arroz.

Bollería y pastelería
  Listo para consumir, dulce horneado: croissants, berlinas, donuts,
  palmeras, napolitanas, magdalenas, bizcochos, hojaldres rellenos
  (bacon-queso, jamón-queso), galletas saladas/dulces tipo bollería.

Dulces y chocolate
  Chocolate, bombones, cacao en polvo (Colacao), caramelos, gominolas,
  regaliz, chicles, miel, mermelada, crema de cacao/nutella, azúcar,
  edulcorantes, siropes.

Bebidas
  Agua, refrescos, zumos, cerveza, vino, cava, energéticas, batidos,
  bebidas vegetales. (Café/infusiones tienen categoría propia.)

Café e infusiones
  Café (grano/molido/cápsulas/soluble), té, manzanilla, tila, poleo,
  achicoria, cebada soluble.

Droguería
  Limpieza del hogar: detergente, suavizante, lejía, multiusos,
  papel de cocina/vegetal, film, aluminio, bolsas de basura, esponjas.

Higiene personal
  Papel higiénico, gel, champú, dentífrico, desodorante, maquinillas,
  compresas/tampones, pañales, toallitas, crema corporal/facial, solar.

Congelados
  Cualquier producto congelado (manda el estado de conservación):
  verdura/fruta congelada, pizza, gyozas, croquetas, helados, marisco
  o carne congelados, patatas prefritas.

  Precocinados vendidos en el lineal de congelados (caprichos, delicias,
  nuggets, croquetas, fingers, rebozados): siempre Congelados, aunque el
  nombre sugiera Carnes, Lácteos u otra categoría.

Snacks y aperitivos
  Patatas fritas, palomitas, gusanitos, nachos, pipas, frutos secos,
  aceitunas, anchoas (aperitivo), barritas de cereales, crackers salados.

Huevos
  Huevos frescos, cualquier formato/pack.

Cereales y pasta
  Arroz, pasta seca, cereales de desayuno, copos de avena, fideos de
  cristal, cuscús, quinoa, bulgur.

Legumbres
  Secas o cocidas/en bote: garbanzos, lentejas, alubias, edamame.

Aceites y grasas
  Aceite de oliva/girasol/coco, manteca, ghee, margarina.
  (Mantequilla → Lácteos.)

Salsas y conservas
  Salsas (tomate frito, ketchup, mayonesa, mostaza, pesto, soja),
  conservas vegetales (maíz, pimiento, alcachofa en lata/bote),
  cremas y patés (hummus, crema de cacahuete, tahin), encurtidos.
  (Legumbres en bote → Legumbres. Aceite → Aceites y grasas.)

Platos preparados
  Cocinado y listo para comer/calentar: tortilla de patata, ensaladilla
  rusa, gazpacho/salmorejo, lasaña/canelones, sushi, bocadillos
  envasados, ensaladas con proteína. No confundir con Pan/Bollería.

Especias y condimentos
  Especias secas, sal, caldos, levadura, bicarbonato, maicena, vinagres.
  (Salsas líquidas → Salsas y conservas.)

Parafarmacia
  Vitaminas, suplementos, proteína en polvo/barritas, colágeno,
  medicamentos sin receta, tiritas, termómetros, test embarazo.

Mascotas
  Comida y accesorios para perro/gato, arena, antiparasitarios.

Otros
  Bazar, papelería, pilas, bombillas, bolsas reutilizables, lo que no
  encaje en ninguna categoría anterior.



═══════════════════════════════════════════════════════════
7. BRAND
═══════════════════════════════════════════════════════════
A) Marca de fabricante visible (Coca-Cola, Danone, Colgate...) → úsala,
   elimínala del "name".

B) Envasado/manufacturado sin marca de fabricante:
   Mercadona: alimentación→"Hacendado" · higiene/cosmética→"Deliplus"
              · limpieza→"Bosque Verde"
   Dia:       higiene/cosmética→"Imaqe" · alimentación→"Dia"
   Lidl:      lácteos→"Milbona" · detergentes→"Pilos" · asiática→"Vitasia"
              · cosmética→"Cien" · si no se identifica→"Lidl"
   Aldi:      sub-marca si se reconoce, si no→"Aldi"
   Carrefour→"Carrefour" · Alcampo→"Auchan" · Eroski→"Eroski"
   Consum→"Consum" · Caprabo→"Caprabo" · El Corte Inglés→"El Corte Inglés"
   Simply→"Simply"
   Supermercado no listado + envasado sin marca visible → usa el nombre
   del propio supermercado. Si no hay confianza → null.

C) Fresco a granel (fruta, verdura, carne, pescado) → null, salvo marca
   explícita ("Jamón Serrano Navidul", "Pollo Coren").

Códigos de artículo en el nombre (frecuente en Lidl/Aldi bazar) → elimínalos
del "name". Ej: "ESPUMADOR-0508364" → name="Espumador de leche", brand="Lidl"

En caso de duda razonable → null antes que inventar.

═══════════════════════════════════════════════════════════
8. NOMBRES
═══════════════════════════════════════════════════════════
"name": normalizado, legible, formato título, sin cantidades ni marca.
"original_name": exacto tal cual aparece en el ticket.

Abreviaturas frecuentes: TOM→Tomate · MANZ→Manzana · Q.→Queso
HIGIE/HIGIENICO→Higiénico · NAT/NTRAL→Natural · PAT→Patata
C/CEB→con cebolla · CONGELA→congelado/a · S.AZ→sin azúcar
UND→unidades (ej. "2 UND"→"(2 uds)" al final del name)
"24 HUEVOS FRESCOS"→"Huevos frescos (pack 24 uds)"

═══════════════════════════════════════════════════════════
9. CAMPOS DE PRECIO
═══════════════════════════════════════════════════════════
original_unit_price: precio/unidad o /kg antes de descuento (positivo)
discount: importe descontado en € (positivo, 0.0 si no hay)
final_unit_price: original_unit_price − discount (unidades)
                  (line_total − discount) / quantity (peso variable)
line_total: importe final de la línea
quantity: nº unidades o peso en kg · unit: "kg"/"unidad"/"litro"/"g"

═══════════════════════════════════════════════════════════
10. SOURCE / VALORES FALTANTES
═══════════════════════════════════════════════════════════
source: "Email" si no se especifica.
No inventes productos, precios, cantidades ni direcciones.
Falta un dato → null (nunca cadena vacía en campos numéricos).
time y brand son opcionales → pueden ser null.
Si no puedes determinar categoría → "Otros".
"""



def _call_gemini(file_bytes: bytes, mime_type: str):
    """Single Gemini API call."""
    prompt = _PROMPT + build_examples_block()
    return client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            types.Part.from_text(text=prompt),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )


def _parse_response(response) -> dict:
    """Strip markdown fences and parse JSON from a Gemini response."""
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def extract_ticket_data(file_bytes: bytes, mime_type: str) -> dict:
    """
    Extract structured ticket data from a PDF or image using Gemini 2.5 Flash.
    Retries once automatically if Gemini returns malformed JSON.
    """
    logger.info(f"Sending {mime_type} ({len(file_bytes)} bytes) to Gemini 2.5 Flash OCR...")

    response = _call_gemini(file_bytes, mime_type)

    # Attempt 1
    try:
        data = _parse_response(response)
        logger.info("Gemini OCR extraction successful.")
        return data
    except json.JSONDecodeError as e:
        logger.warning(f"Gemini returned malformed JSON (attempt 1): {e} — retrying...")

    # Attempt 2
    try:
        response = _call_gemini(file_bytes, mime_type)
        data = _parse_response(response)
        logger.info("Gemini OCR extraction successful on retry.")
        return data
    except Exception as e:
        logger.error(f"Gemini returned malformed JSON after retry: {e}")
        logger.error(f"Raw response: {response.text.strip()}")
        raise