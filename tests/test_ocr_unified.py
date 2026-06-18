import json
from datetime import datetime, time
from unittest.mock import patch, MagicMock

from src.ocr.unified import extract_ticket_data


def test_extract_ticket_data():
    fake_json = {
        "supermercado": "Mercadona",
        "fecha": "2024-06-12",
        "hora": "12:33",
        "tienda": "Zaragoza - Actur",
        "productos": [
            {
                "nombre": "Leche Entera",
                "cantidad": 1,
                "precio_unitario": 0.95,
                "precio_total": 0.95,
                "categoria": "Lácteos",
                "unidad_medida": "unidad",
                "tipo_precio": "unidad",
                "oferta": False,
                "descuento": 0.0
            }
        ],
        "total": 0.95
    }

    fake_response = MagicMock()
    fake_response.text = json.dumps(fake_json)

    with patch("src.ocr.unified.client.models.generate_content") as mock_gen:
        mock_gen.return_value = fake_response

        result = extract_ticket_data(b"fake_bytes", "application/pdf")

        assert result["supermercado"] == "Mercadona"
        assert result["total"] == 0.95
        assert len(result["productos"]) == 1
        assert result["productos"][0]["nombre"] == "Leche Entera"


