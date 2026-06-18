from __future__ import annotations

import json
from google import genai
from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)

client = genai.Client(api_key=settings.anthropic_api_key) 

def extract_ticket_data(file_bytes: bytes, mime_type: str) -> dict:
    """
    Extract structured ticket data from a PDF or image using Gemini.
    Returns a dict with supermarket, date, products, totals, etc.
    """

    logger.info(f"Sending {mime_type} ({len(file_bytes)} bytes) to Gemini OCR...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {
                "mime_type": mime_type,
                "data": file_bytes
            },
            {
                "text": """
Eres un sistema experto en lectura de tickets de supermercado.

Tu tarea es analizar el texto del ticket y devolver un JSON ESTRICTO con esta estructura:

{
  "supermercado": "Mercadona",
  "fecha": "2026-06-15",
  "hora": "12:33",
  "tienda": "Zaragoza - Actur",
  "total": 23.45,
  "productos": [
    {
      "nombre": "Tomate pera",
      "categoria": "Verduras",
      "cantidad": 1.25,
      "unidad_medida": "kg",
      "precio_unitario": 2.39,
      "precio_total": 2.99,
      "tipo_precio": "peso",
      "oferta": false,
      "descuento": 0
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
- NO incluyas cantidades, pesos ni unidades en el nombre para productos a peso.
  Ejemplos:
    - "PLT TOM 1KG" → "Tomate pera"
    - "MANZ ROJA 1KG" → "Manzana roja"
    - "CONTRAMUSLO DESHUESA" → "Contramuslo de pollo deshuesado"
- SÍ incluye el formato cuando el producto es un PACK o un producto que se vende por unidades fijas.
  Ejemplos:
    - "HUEV L 12UD" → "Huevos tamaño L (12 unidades)"
    - "PACK 6 AGUA" → "Agua mineral (pack 6)"
    - "YOG NAT 6X125" → "Yogur natural (pack 6)"

3) CANTIDAD Y FORMATO:
- La cantidad comprada debe ir SIEMPRE en los campos:
  - cantidad
  - unidad_medida
  - tipo_precio
- NO debe aparecer en el nombre salvo que forme parte del formato del producto (packs).

4) NO INVENTAR:
- No inventes productos que no aparezcan en el ticket.
- No inventes precios.
- No inventes cantidades.

5) SI FALTA INFORMACIÓN:
- Si no puedes determinar un dato, usa null.
- Si no puedes determinar la categoría, usa "Otros".

6) JSON:
- Devuelve SIEMPRE un JSON válido, sin texto adicional.
- No incluyas explicaciones.
"""
            }
        ]
    )

    raw = response.text.strip()

    try:
        data = json.loads(raw)
        logger.info("Gemini OCR extraction successful.")
        return data
    except Exception as e:
        logger.error(f"Error parsing Gemini JSON: {e}")
        logger.error(f"Raw response: {raw}")
        raise
