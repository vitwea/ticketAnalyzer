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
Eres un sistema experto en lectura de tickets de supermercado españoles.

Tu tarea es analizar el ticket y devolver un JSON ESTRICTO con esta estructura:

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
      "category": "Verduras",
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

════════════════════════════════════════════════════════════
REGLA 1 — NOMBRE DEL SUPERMERCADO
════════════════════════════════════════════════════════════
El campo "supermarket" contiene ÚNICAMENTE el nombre comercial de la cadena,
NUNCA la razón social legal ni el nombre de la franquicia.

Tabla de normalización OBLIGATORIA:
  "MERCADONA, S.A." / "MERCADONA S.A."              → "Mercadona"
  "LIDL SUPERMERCADOS S.A.U." / cualquier "LIDL…"  → "Lidl"
  "DIA, S.A." y CUALQUIER franquicia de Dia         → "Dia"
  "CARREFOUR …"                                     → "Carrefour"
  "ALCAMPO …"                                       → "Alcampo"
  "EROSKI …"                                        → "Eroski"
  "ALDI …"                                          → "Aldi"
  "CONSUM …"                                        → "Consum"

Cómo detectar tickets de Dia con razón social franquiciada:
  Los tickets de franquicias Dia (p.ej. "ALIMENTACION PELLEJERO BRETON, S.L.")
  contienen alguna de estas señales → en ese caso usa SIEMPRE "Dia":
    • "Productos vendidos por Dia"
    • "Total venta Dia"
    • "REF.DIA:" en los datos de la operación
    • Logo o texto "dia" en el ticket digital

════════════════════════════════════════════════════════════
REGLA 2 — TIENDA (STORE)
════════════════════════════════════════════════════════════
Formato OBLIGATORIO: "Dirección (CP, Ciudad)"
  Ejemplo: "Avda. Francisco de Goya, 61 (50005, Zaragoza)"

PRIORIDAD de fuentes (de mayor a menor):
  1. Sección "Compra realizada en" al final del ticket digital (más limpia)
  2. Cabecera del ticket

Normalización de la dirección:
  - Convierte MAYÚSCULAS a formato título: "AVDA. FRANCISCO DE GOYA, 61" → "Avda. Francisco de Goya, 61"
  - Expande abreviaturas comunes: CL/C/ → C/, AVDA → Avda., PZA → Pza., C.C. → C.C.
  - Si la dirección incluye "con C/ …" o "esquina …" (intersección), omite esa parte:
      "C/ Vicente Berdusán, 44, con C/ Italia" → "C/ Vicente Berdusán, 44"

Dirección en Dia: la calle aparece en la cabecera ("CL TOMAS BRETON 46") y el CP+ciudad
  al pie del ticket en los datos de la operación ("CP:50005 Zaragoza").
  Combínalos: "Cl. Tomás Bretón, 46 (50005, Zaragoza)"

Si NO puedes identificar dirección + CP + ciudad con seguridad → usa null. No inventes.

════════════════════════════════════════════════════════════
REGLA 3 — DESCUENTOS DE FIDELIDAD Y PROMOCIONALES
════════════════════════════════════════════════════════════
En tickets de Lidl (y eventualmente otros), los descuentos aparecen como líneas
secundarias INMEDIATAMENTE DESPUÉS del producto al que aplican:

  Nombres que identifican estas líneas de descuento (NO son productos):
    "PROMO LIDL PLUS"
    "Descuento XX%"
    "Desc."
    Cualquier línea indentada con un valor NEGATIVO justo después de un producto

Procesamiento OBLIGATORIO:
  1. NO crees ningún producto con estos nombres.
  2. El valor absoluto (sin signo) es el campo "discount" del producto INMEDIATAMENTE ANTERIOR.
  3. Si hay VARIAS líneas de descuento consecutivas para el mismo producto → SÚMALAS.
  4. final_unit_price = original_unit_price − discount  (para productos por unidad)
     Para productos por peso → ver Regla 4.
  5. Las líneas de resumen al pie del ticket son INFORMATIVAS → ignóralas como productos:
       "Total oferta Lidl Plus: X EUR"
       "Desc. total en compra: X EUR"
  6. Los cupones al final del ticket también son INFORMATIVOS → ignóralos:
       "Cupones canjeados: -3€ para tu próxima compra"
       "-15% Nueces sin cáscara"

Ejemplos reales extraídos de tickets Lidl:

  Ticket muestra:
    BANANA (0,772 kg x 1,49 EUR/kg)   1,15
    PROMO LIDL PLUS                   -0,39
  Resultado:
    quantity=0.772, unit="kg", original_unit_price=1.49,
    discount=0.39, final_unit_price=1.10, line_total=0.85
  [El discount es el importe total descontado en la línea, no sobre el precio/kg]

  Ticket muestra:
    GRIEGO NATURAL   1,49
    Desc.            -0,10
  Resultado:
    quantity=1, unit="unidad", original_unit_price=1.49,
    discount=0.10, final_unit_price=1.39, line_total=1.39

  Ticket muestra:
    TRÍO DE HUMMUS   2,49
    Descuento 20%    -0,50
  Resultado:
    quantity=1, unit="unidad", original_unit_price=2.49,
    discount=0.50, final_unit_price=1.99, line_total=1.99

  Ticket muestra:
    NUEZ NATURAL     2,69
    PROMO LIDL PLUS  -0,40
    PROMO LIDL PLUS  -0,70
  Resultado:
    discount=1.10 (suma de ambos), final_unit_price=1.59, line_total=1.59

  Ticket muestra:
    HUMMUS           1,15
    PROMO LIDL PLUS  -0,17
    PROMO LIDL PLUS  -0,30
  Resultado:
    discount=0.47, final_unit_price=0.68, line_total=0.68

════════════════════════════════════════════════════════════
REGLA 4 — PRODUCTOS DE PESO VARIABLE
════════════════════════════════════════════════════════════
Un producto de peso variable ocupa 1 o 2 líneas:

  Formato A (Mercadona / Lidl ticket 1):
    NOMBRE DEL PRODUCTO
      X,XXX kg  Y,YY €/kg   Z,ZZ        ← segunda línea con peso y precio/kg

  Formato B (Lidl ticket 2):
    NOMBRE DEL PRODUCTO   Z,ZZ
      X,XXX kg x Y,YY  EUR/kg            ← segunda línea debajo

  Formato C (Dia):
    NOMBRE   X,XXXkg   Y,YY €/kg   Z,ZZ € ← todo en una línea

En todos los casos:
  quantity           = el peso en kg (ej. 0.942)
  unit               = "kg"
  original_unit_price = el precio POR KG (ej. 1.90) — NO el importe total
  line_total         = el importe final de la línea (ej. 1.79)

Si el producto tiene además un descuento de fidelidad (PROMO LIDL PLUS, etc.):
  discount           = importe total descontado sobre la línea (ej. 0.30)
  final_unit_price   = (line_total − discount) / quantity  redondeado a 2 decimales
    Ejemplo: PIMIENTO ROJO  0,338 kg x 2,89 EUR/kg  0,98 → PROMO -0,30
      discount=0.30, line_total=0.68, final_unit_price=0.68/0.338 ≈ 2.01

Si NO hay descuento:
  discount           = 0.0
  final_unit_price   = original_unit_price

════════════════════════════════════════════════════════════
REGLA 5 — CANTIDAD Y PRECIO UNITARIO EN MERCADONA
════════════════════════════════════════════════════════════
En Mercadona, cuando se compra más de una unidad de un mismo producto,
el ticket muestra: CANTIDAD  NOMBRE  P.UNIT  IMPORTE_TOTAL
  Ejemplo: "2 ARROZ CAMPESTRE  2,00  4,00"
    → quantity=2, unit="unidad", original_unit_price=2.00, line_total=4.00

  Ejemplo: "2 Q. UNTAR SUAVE  1,40  2,80"
    → quantity=2, unit="unidad", original_unit_price=1.40, line_total=2.80

════════════════════════════════════════════════════════════
REGLA 6 — CATEGORÍAS FIJAS
════════════════════════════════════════════════════════════
Elige EXACTAMENTE UNA:
  Lácteos · Carnes · Pescados · Frutas · Verduras · Panadería · Bebidas
  Droguería · Higiene · Congelados · Snacks · Huevos · Cereales y pasta
  Salsas y conservas · Otros

Guía de categorías para productos frecuentes:
  Bolsa de plástico / bolsa de tela           → Otros
  Papel higiénico / papel de cocina           → Higiene
  Papel vegetal / film / papel de horno       → Droguería
  Tortilla de patata (precocinada)            → Otros
  Delicias de pollo / nuggets / rebozados     → Carnes
  Frutos secos (nueces, almendras...)         → Snacks
  Hummus                                      → Salsas y conservas
  Gyozas / dumpling                           → Congelados
  Artículos de bazar / no-alimentación        → Otros
  Fideos de cristal / pasta                   → Cereales y pasta
  Crema de cacahuete                          → Salsas y conservas
  Chocolate                                   → Snacks
  Frutos rojos congelados                     → Congelados
  Yogur griego                                → Lácteos
  Desodorante / higiene personal              → Higiene
  Gambas / mariscos                           → Pescados
  Mantequilla                                 → Lácteos
  Queso                                       → Lácteos
  Nata                                        → Lácteos

════════════════════════════════════════════════════════════
REGLA 7 — MARCA (BRAND)
════════════════════════════════════════════════════════════
Orden de decisión:

CASO A — Marca de fabricante visible en el ticket:
  Si el ticket menciona una marca reconocible (Coca-Cola, Danone, Colgate...) → úsala.

CASO B — Producto ENVASADO/MANUFACTURADO sin marca de fabricante:
  Asigna la marca blanca del supermercado:
    Mercadona:
      alimentación general          → "Hacendado"
      higiene y cosmética           → "Deliplus"
      limpieza del hogar            → "Bosque Verde"
    Carrefour                       → "Carrefour"
    Alcampo                         → "Auchan"
    Eroski                          → "Eroski"
    Dia:
      higiene/cosmética             → "Imaqe"  (marca propia de Dia)
      alimentación general          → "Dia"
    Lidl: usa la sub-marca si la reconoces con seguridad (Milbona, Pilos, Vitasia, Cien...);
          si no → "Lidl"
    Aldi: ídem con sus sub-marcas; si no → "Aldi"

CASO C — Producto fresco a granel (fruta, verdura, carne, pescado, charcutería suelta):
  → "brand": null  (salvo que el ticket indique explícitamente una marca)

En caso de duda razonable → null antes que inventar.

Productos con código de artículo en el nombre (frecuente en Lidl bazar):
  "ESPUMADOR-0508364" → name="Espumador de leche", brand="Lidl" (es producto de bazar Lidl)
  "FLOOPY ZEBRA"      → name="Peluche cebra Floopy", brand="Lidl", category="Otros"
  Elimina siempre el código numérico del campo "name".

════════════════════════════════════════════════════════════
REGLA 8 — NOMBRES DE PRODUCTO
════════════════════════════════════════════════════════════
  "name"          : nombre NORMALIZADO, legible, sin cantidades ni marca.
                    Completa abreviaturas. Usa formato título.
  "original_name" : nombre EXACTO tal como aparece en el ticket, sin modificar.

Expansión de abreviaturas frecuentes en tickets españoles:
  PLT        → "pellet" o referencia interna → omite del nombre
  TOM        → Tomate
  MANZ       → Manzana
  Q.         → Queso
  HIGIE/HIGIENICO → Higiénico (papel)
  DOBLE ROLL → Doble rollo
  NAT/NTRAL  → Natural
  PAT        → Patata
  C/CEB      → con cebolla
  CONGELA    → congelado/a
  S.AZ       → sin azúcar
  UND        → unidades
  2 UND en el nombre → "(2 uds)" al final del name
  24 HUEVOS FRESCOS → "Huevos frescos (pack 24 uds)", category="Huevos"

Si la marca se extrae del nombre y el resto queda ambiguo → completa para que sea descriptivo.

════════════════════════════════════════════════════════════
REGLA 9 — CAMPOS DE PRECIO (resumen)
════════════════════════════════════════════════════════════
  original_unit_price : precio por unidad/kg ANTES de descuentos (siempre positivo)
  discount            : importe descontado en € — SIEMPRE positivo (0.0 si no hay descuento)
  final_unit_price    : original_unit_price − discount  (para unidades)
                        (line_total − discount) / quantity  (para peso variable con descuento)
  line_total          : importe total de la línea tal como figura en el ticket
  quantity            : número de unidades o peso en kg
  unit                : "kg", "unidad", "litro", "g", etc.

════════════════════════════════════════════════════════════
REGLA 10 — FUENTE (SOURCE)
════════════════════════════════════════════════════════════
Si no se especifica, usa "Email".

════════════════════════════════════════════════════════════
REGLA 11 — NO INVENTAR / VALORES FALTANTES
════════════════════════════════════════════════════════════
  - No inventes productos que no aparezcan en el ticket.
  - No inventes precios, cantidades ni direcciones.
  - Si falta un dato → null (nunca cadena vacía para campos numéricos).
  - "time" y "brand" son opcionales → pueden ser null.
  - Si no puedes determinar la categoría → "Otros".

════════════════════════════════════════════════════════════
REGLA 12 — SALIDA JSON
════════════════════════════════════════════════════════════
  - Devuelve SIEMPRE un JSON válido.
  - Sin texto adicional, sin explicaciones, sin bloques de código markdown.
  - Usa punto (.) como separador decimal, nunca coma.
"""),
        ],

        generation_config={
            "response_mime_type": "application/json"
        }
    )

    raw = response.text.strip()

    # Strip markdown fences if Gemini wraps in ```json ... ```
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