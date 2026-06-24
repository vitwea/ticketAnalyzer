import json
from unittest.mock import patch, MagicMock

from src.ocr.unified import extract_ticket_data


def test_extract_ticket_data():
    fake_json = {
        "supermarket": "Mercadona",
        "date": "2024-06-12",
        "time": "12:33",
        "store": "Pza. Roma, s/n (50010, Zaragoza)",
        "source": "Email",
        "total": 0.95,
        "products": [
            {
                "name": "Leche entera",
                "original_name": "LECHE ENTERA",
                "category": "Lácteos",
                "brand": "Hacendado",
                "quantity": 1,
                "unit": "unidad",
                "original_unit_price": 0.95,
                "discount": 0.0,
                "final_unit_price": 0.95,
                "line_total": 0.95,
            }
        ],
    }

    fake_response = MagicMock()
    fake_response.text = json.dumps(fake_json)

    with patch("src.ocr.unified.client.models.generate_content") as mock_gen:
        mock_gen.return_value = fake_response

        result = extract_ticket_data(b"fake_bytes", "application/pdf")

        assert result["supermarket"] == "Mercadona"
        assert result["total"] == 0.95
        assert len(result["products"]) == 1
        p = result["products"][0]
        assert p["name"] == "Leche entera"
        assert p["brand"] == "Hacendado"
        assert p["discount"] == 0.0
        assert p["final_unit_price"] == 0.95


def test_extract_ticket_data_with_lidl_discount():
    """Verifies that PROMO LIDL PLUS lines are absorbed into discount, not as products."""
    fake_json = {
        "supermarket": "Lidl",
        "date": "2026-05-12",
        "time": "21:06",
        "store": "C/ Vicente Berdusán, 44 (50010, Zaragoza)",
        "source": "Email",
        "total": 8.62,
        "products": [
            {
                "name": "Gyozas de verduras",
                "original_name": "GYOZAS DE VERDURAS",
                "category": "Congelados",
                "brand": "Lidl",
                "quantity": 1,
                "unit": "unidad",
                "original_unit_price": 2.49,
                "discount": 0.0,
                "final_unit_price": 2.49,
                "line_total": 2.49,
            },
            {
                "name": "Banana",
                "original_name": "BANANA",
                "category": "Frutas",
                "brand": None,
                "quantity": 0.772,
                "unit": "kg",
                "original_unit_price": 1.49,
                "discount": 0.39,
                "final_unit_price": 1.10,
                "line_total": 0.85,
            },
            {
                "name": "Trío de hummus",
                "original_name": "TRÍO DE HUMMUS",
                "category": "Salsas y conservas",
                "brand": "Lidl",
                "quantity": 1,
                "unit": "unidad",
                "original_unit_price": 2.49,
                "discount": 0.50,
                "final_unit_price": 1.99,
                "line_total": 1.99,
            },
        ],
    }

    fake_response = MagicMock()
    fake_response.text = json.dumps(fake_json)

    with patch("src.ocr.unified.client.models.generate_content") as mock_gen:
        mock_gen.return_value = fake_response

        result = extract_ticket_data(b"fake_bytes", "application/pdf")

        # No product named "PROMO LIDL PLUS" should exist
        names = [p["name"] for p in result["products"]]
        assert not any("promo" in n.lower() or "lidl plus" in n.lower() for n in names)

        # Banana: weight-variable with discount
        banana = next(p for p in result["products"] if "banana" in p["name"].lower())
        assert banana["quantity"] == 0.772
        assert banana["unit"] == "kg"
        assert banana["discount"] == 0.39

        # Hummus: discount absorbed correctly
        hummus = next(p for p in result["products"] if "hummus" in p["name"].lower())
        assert hummus["discount"] == 0.50
        assert hummus["final_unit_price"] == 1.99


def test_extract_ticket_data_strips_markdown():
    """Verifies that markdown code fences are stripped before JSON parsing."""
    fake_json = {"supermarket": "Dia", "date": "2026-06-23", "time": "11:56",
                 "store": "Cl. Tomás Bretón, 46 (50005, Zaragoza)", "source": "Email",
                 "total": 16.22, "products": []}

    fake_response = MagicMock()
    fake_response.text = "```json\n" + json.dumps(fake_json) + "\n```"

    with patch("src.ocr.unified.client.models.generate_content") as mock_gen:
        mock_gen.return_value = fake_response
        result = extract_ticket_data(b"fake_bytes", "application/pdf")
        assert result["supermarket"] == "Dia"