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

── CAPA 1: supermercados conocidos (normalización exacta) ──
  "MERCADONA, S.A." / "MERCADONA S.A."              → "Mercadona"
  "LIDL SUPERMERCADOS S.A.U." / cualquier "LIDL…"  → "Lidl"
  "DIA, S.A." y CUALQUIER franquicia de Dia         → "Dia"
  "CARREFOUR …"                                     → "Carrefour"
  "ALCAMPO …"                                       → "Alcampo"
  "EROSKI …"                                        → "Eroski"
  "ALDI …"                                          → "Aldi"
  "CONSUM …"                                        → "Consum"
  "CAPRABO …"                                       → "Caprabo"
  "AHORRAMAS …"                                     → "Ahorramas"
  "CONDIS …"                                        → "Condis"
  "GADIS …"                                         → "Gadis"
  "EL CORTE INGLÉS …" / "SUPERCOR …"               → "El Corte Inglés"
  "SIMPLY …"                                        → "Simply"
  "SUPERSOL …" / "COALIMENT …"                      → "Supersol"

── CAPA 2: supermercado desconocido (regla general) ──
  Si la cabecera no coincide con ninguno de los anteriores:
  1. Busca el nombre comercial en logos, textos destacados o cabecera del ticket.
  2. Elimina la forma jurídica: S.A., S.L., S.A.U., S.C., S.L.U., S.COOP., C.B. y similares.
  3. Elimina el NIF/CIF (letra + 8 dígitos) si aparece junto al nombre.
  4. Usa el nombre resultante en formato título (primera letra mayúscula).
     Ejemplo: "SUPERMERCADOS PACO GARCIA, S.L. B12345678" → "Supermercados Paco Garcia"

── DETECCIÓN DE FRANQUICIAS ──
  Algunos tickets muestran la razón social del franquiciado en cabecera pero
  el nombre real de la cadena aparece en el cuerpo del ticket.
  Señales que identifican la cadena real (aplica con cualquier supermercado):
    • "Productos vendidos por X" → cadena = X
    • "Total venta X"           → cadena = X
    • "REF.X:" en datos de operación → cadena = X
    • Logo o marca visible en el ticket digital

════════════════════════════════════════════════════════════
REGLA 2 — TIENDA (STORE)
════════════════════════════════════════════════════════════
Formato OBLIGATORIO: "Dirección (CP, Ciudad)"
  Ejemplo: "Avda. Francisco de Goya, 61 (50005, Zaragoza)"

PRIORIDAD de fuentes (de mayor a menor):
  1. Sección "Compra realizada en" / "Datos de la tienda" al final del ticket digital
  2. Cabecera del ticket
  3. Pie del ticket (datos de la operación)

Normalización de la dirección:
  - Convierte MAYÚSCULAS a formato título: "AVDA. FRANCISCO DE GOYA, 61" → "Avda. Francisco de Goya, 61"
  - Expande abreviaturas: CL → C/, AVDA → Avda., PZA → Pza., URB → Urb., C.C. → C.C.
  - Si la dirección incluye intersección ("con C/ …", "esq. …", "esquina …"), omite esa parte:
      "C/ Vicente Berdusán, 44, con C/ Italia" → "C/ Vicente Berdusán, 44"

Cuando dirección y CP/ciudad están en zonas distintas del ticket:
  Algunos tickets (p.ej. Dia) muestran la calle en la cabecera y el CP+ciudad
  en el pie (formato "CP:50005 Zaragoza" o "C.P.: 50005 - Zaragoza").
  En ese caso combina ambas partes en el formato estándar.
  Aplica esta lógica con CUALQUIER supermercado, no solo Dia.

Si NO puedes identificar dirección + CP + ciudad con seguridad → usa null. No inventes.

════════════════════════════════════════════════════════════
REGLA 3 — DESCUENTOS DE FIDELIDAD Y PROMOCIONALES
════════════════════════════════════════════════════════════
En cualquier supermercado, los descuentos sobre un producto concreto aparecen
como líneas secundarias INMEDIATAMENTE DESPUÉS del producto al que aplican.

Patrones que identifican una línea de descuento (NO es un producto):
  • Texto que contiene "PROMO", "Descuento", "Desc.", "DTO.", "Oferta", "Promoción"
    seguido de un valor negativo
  • Cualquier línea con valor NEGATIVO indentada justo después de un producto
  • Nombres de programas de fidelidad de cualquier cadena:
      "PROMO LIDL PLUS", "Club Carrefour", "Descuento Dia Card",
      "Ahorro Eroski", "Tarjeta Alcampo", o similar

Procesamiento OBLIGATORIO (aplica a CUALQUIER supermercado):
  1. NO crees ningún producto con estos nombres.
  2. El valor absoluto (sin signo) es el campo "discount" del producto INMEDIATAMENTE ANTERIOR.
  3. Si hay VARIAS líneas de descuento consecutivas para el mismo producto → SÚMALAS.
  4. final_unit_price = original_unit_price − discount  (para productos por unidad)
     Para productos por peso → ver Regla 4.
  5. Las líneas de resumen al pie del ticket son INFORMATIVAS → ignóralas:
       "Total oferta Lidl Plus: X EUR"
       "Desc. total en compra: X EUR"
       "Ahorro total: X EUR"
       Cualquier línea de totales de descuento al final del ticket
  6. Los cupones para futuras compras también son INFORMATIVOS → ignóralos:
       "Cupones canjeados: -3€ para tu próxima compra"
       "-15% Nueces sin cáscara"

Ejemplos reales (tickets Lidl):

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
REGLA 5 — CANTIDAD Y PRECIO UNITARIO (MÚLTIPLES UNIDADES)
════════════════════════════════════════════════════════════
Cuando se compran varias unidades del mismo producto, muchos supermercados
muestran la cantidad al inicio de la línea seguida del precio unitario y el total:
  Formato habitual: CANTIDAD  NOMBRE  P.UNIT  IMPORTE_TOTAL

  Ejemplos (Mercadona):
    "2 ARROZ CAMPESTRE  2,00  4,00"   → quantity=2, original_unit_price=2.00, line_total=4.00
    "2 Q. UNTAR SUAVE   1,40  2,80"  → quantity=2, original_unit_price=1.40, line_total=2.80

  Otros formatos equivalentes que pueden aparecer en cualquier supermercado:
    "3 x 1,50"      → quantity=3, original_unit_price=1.50, line_total=4.50
    "NOMBRE  x3  1,50  4,50"  → ídem

En todos los casos: original_unit_price es el precio POR UNIDAD, no el total.

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
Orden de decisión (aplica en este orden estricto):

CASO A — Marca de fabricante visible en el ticket:
  Si el ticket menciona una marca comercial reconocible (Coca-Cola, Danone,
  Colgate, Pascual, Nestlé, Kellogg's, Heinz, Fairy, Ariel...) → úsala en
  "brand" y elimínala del campo "name".

CASO B — Producto ENVASADO/MANUFACTURADO sin marca de fabricante:

  ── CAPA 1: supermercados conocidos ──
    Mercadona:
      alimentación general   → "Hacendado"
      higiene y cosmética    → "Deliplus"
      limpieza del hogar     → "Bosque Verde"
    Dia:
      higiene y cosmética    → "Imaqe"
      alimentación general   → "Dia"
    Lidl: usa la sub-marca si la reconoces con seguridad:
      lácteos                → "Milbona"
      detergentes            → "Pilos"
      comida asiática        → "Vitasia"
      cosmética/higiene      → "Cien"
      si no la identificas   → "Lidl"
    Aldi: ídem con sus sub-marcas; si no la identificas → "Aldi"
    Carrefour                → "Carrefour"
    Alcampo                  → "Auchan"
    Eroski                   → "Eroski"
    Consum                   → "Consum"
    Caprabo                  → "Caprabo"
    El Corte Inglés          → "El Corte Inglés"
    Simply                   → "Simply"

  ── CAPA 2: supermercado no listado ──
    Si el supermercado no aparece en la tabla anterior pero el producto
    es claramente envasado/manufacturado y de marca blanca:
    → usa el nombre comercial del supermercado como brand.
    Ejemplo: supermercado "Supersol", producto envasado sin marca visible
    → brand = "Supersol"
    Si no puedes determinar con confianza si es marca blanca → brand = null.

CASO C — Producto fresco a granel (fruta, verdura, carne, pescado, charcutería suelta):
  → "brand": null  (salvo que el ticket indique explícitamente una marca,
    p.ej. "Jamón Serrano Navidul" o "Pollo Coren")

En caso de duda razonable → null antes que inventar.

Productos con código de artículo en el nombre (frecuente en Lidl y Aldi bazar):
  "ESPUMADOR-0508364" → name="Espumador de leche", brand="Lidl"
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