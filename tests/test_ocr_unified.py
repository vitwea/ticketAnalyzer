import json
from unittest.mock import patch

from src.ocr.unified import extract_ticket_data


def test_extract_ticket_data():
    fake_json = {
        "supermercado": "Mercadona",
        "fecha": "2024-06-12",
        "productos": [
            {
                "nombre": "Leche Entera",
                "cantidad": 1,
                "precio_unitario": 0.95,
                "precio_total": 0.95,
                "categoria": "Lácteos"
            }
        ],
        "total": 23.45
    }

    fake_response = type("FakeResponse", (), {"text": json.dumps(fake_json)})

    with patch("src.ocr.unified.client.models.generate_content") as mock_gen:
        mock_gen.return_value = fake_response

        result = extract_ticket_data(b"fake_bytes", "application/pdf")

        assert result["supermercado"] == "Mercadona"
        assert result["total"] == 23.45
        assert len(result["productos"]) == 1