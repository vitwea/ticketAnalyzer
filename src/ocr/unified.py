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
  "store": "Zaragoza - Actur",
  "source": "Email",
  "total": 23.45,
  "products": [
    {
      "name": "Tomate pera",
      "original_name": "PLT TOM",
      "category": "Verduras",
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

2) NOMBRES DE PRODUCTO:
- COMPLETA nombres truncados o abreviados usando conocimiento general de productos de supermercado.
- El campo "name" debe contener el nombre normalizado, sin cantidades ni unidades (excepto para packs).
- El campo "original_name" debe contener el nombre tal como aparece en el ticket.
- Ejemplos:
    - original_name: "PLT TOM 1KG" → name: "Tomate pera"
    - original_name: "MANZ ROJA 1KG" → name: "Manzana roja"
    - original_name: "HUEV L 12UD" → name: "Huevos tamaño L (12 unidades)"

3) PRECIOS Y CANTIDADES:
- original_unit_price: precio por unidad ANTES de descuentos
- discount: cantidad descontada (0 si no hay descuento)
- final_unit_price: precio final por unidad DESPUÉS de descuentos (original_unit_price - discount)
- line_total: precio total de la línea (quantity × final_unit_price)
- quantity: cantidad comprada
- unit: unidad de medida (kg, unidad, litro, etc.)

4) NO INVENTAR:
- No inventes productos que no aparezcan en el ticket.
- No inventes precios.
- No inventes cantidades.

5) SI FALTA INFORMACIÓN:
- Si no puedes determinar un dato, usa null.
- Si no puedes determinar la categoría, usa "Otros".
- El campo "time" es opcional, puede ser null.

6) JSON:
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