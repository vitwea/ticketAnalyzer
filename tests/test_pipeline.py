import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.etl.pipeline import run_pipeline, _validate_ticket_json, _parse_store
from src.db.connection import Base


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_product(**overrides):
    base = {
        "name": "Pan",
        "original_name": "PAN",
        "category": "Panadería",
        "brand": None,
        "quantity": 1,
        "unit": "unidad",
        "original_unit_price": 1.0,
        "discount": 0.0,
        "final_unit_price": 1.0,
        "line_total": 1.0,
    }
    base.update(overrides)
    return base


def _make_ticket(**overrides):
    base = {
        "supermarket": "Mercadona",
        "date": "2024-06-12",
        "time": "14:08",
        "store": "Pza. Roma, s/n (50010, Zaragoza)",
        "source": "Email",
        "total": 1.0,
        "products": [_make_product()],
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────
# _validate_ticket_json
# ─────────────────────────────────────────────

def test_validate_ticket_json_passes_valid():
    _validate_ticket_json(_make_ticket())  # should not raise


def test_validate_ticket_json_missing_top_level_field():
    for field in ["supermarket", "date", "total", "products"]:
        ticket = _make_ticket()
        del ticket[field]
        with pytest.raises(ValueError, match=field):
            _validate_ticket_json(ticket)


def test_validate_ticket_json_missing_product_field():
    required = [
        "name", "category", "quantity", "unit",
        "original_unit_price", "discount", "final_unit_price", "line_total",
    ]
    for field in required:
        ticket = _make_ticket(products=[_make_product(**{field: None})])
        with pytest.raises(ValueError, match=field):
            _validate_ticket_json(ticket)


def test_validate_ticket_json_products_not_list():
    ticket = _make_ticket(products="not a list")
    with pytest.raises(ValueError, match="list"):
        _validate_ticket_json(ticket)


# ─────────────────────────────────────────────
# _parse_store
# ─────────────────────────────────────────────

@pytest.mark.parametrize("store_str,expected_address,expected_cp,expected_city", [
    (
        "Avda. Francisco de Goya, 61 (50005, Zaragoza)",
        "Avda. Francisco de Goya, 61", "50005", "Zaragoza",
    ),
    (
        "Pza. Roma, s/n (50010, Zaragoza)",
        "Pza. Roma, s/n", "50010", "Zaragoza",
    ),
    (
        "C/ Vicente Berdusán, 44 (50010, Zaragoza)",
        "C/ Vicente Berdusán, 44", "50010", "Zaragoza",
    ),
    (
        "Cl. Tomás Bretón, 46 (50005, Zaragoza)",
        "Cl. Tomás Bretón, 46", "50005", "Zaragoza",
    ),
    # Fallback: no parens
    (
        "Avda. Francisco de Goya, 61 50005 Zaragoza",
        "Avda. Francisco de Goya, 61", "50005", "Zaragoza",
    ),
])
def test_parse_store_valid(store_str, expected_address, expected_cp, expected_city):
    result = _parse_store(store_str)
    assert result is not None
    address, cp, city, province, country = result
    assert address == expected_address
    assert cp == expected_cp
    assert city == expected_city
    assert country == "Spain"


def test_parse_store_none_input():
    assert _parse_store(None) is None


def test_parse_store_unparseable():
    assert _parse_store("dirección sin código postal") is None


# ─────────────────────────────────────────────
# run_pipeline (integration with mocks)
# ─────────────────────────────────────────────

@pytest.fixture()
def in_memory_db(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:", future=True)
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(test_engine)

    monkeypatch.setattr("src.db.connection.engine", test_engine)
    monkeypatch.setattr("src.db.insert.connection.engine", test_engine)
    monkeypatch.setattr("src.db.connection.SessionLocal", lambda: TestingSession())
    monkeypatch.setattr("src.db.insert.connection.SessionLocal", lambda: TestingSession())

    yield test_engine
    Base.metadata.drop_all(test_engine)


def test_pipeline_inserts_receipt(monkeypatch, in_memory_db):
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "msg123"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda msg_id: [("ticket.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: _make_ticket(),
    )

    inserted = run_pipeline("from:mercadona")

    assert len(inserted) == 1
    assert isinstance(inserted[0], int)


def test_pipeline_idempotent(monkeypatch, in_memory_db):
    """Running the pipeline twice for the same gmail_id must not duplicate the receipt."""
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "msg123"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda msg_id: [("ticket.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: _make_ticket(),
    )

    first  = run_pipeline("from:mercadona")
    second = run_pipeline("from:mercadona")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


def test_pipeline_skips_failed_attachment(monkeypatch, in_memory_db):
    """A bad attachment should be skipped; other messages still process."""
    calls = iter([
        [("bad.pdf",    "application/pdf", b"bad")],
        [("good.pdf",   "application/pdf", b"good")],
    ])

    monkeypatch.setattr(
        "src.etl.pipeline.list_messages",
        lambda q: [{"id": "msg_bad"}, {"id": "msg_good"}],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda msg_id: next(calls),
    )

    def fake_ocr(data, mime):
        if data == b"bad":
            raise ValueError("OCR failed")
        return _make_ticket(products=[_make_product()])

    monkeypatch.setattr("src.etl.pipeline.extract_ticket_data", fake_ocr)

    inserted = run_pipeline("from:mercadona")
    assert len(inserted) == 1


def test_pipeline_lidl_ticket(monkeypatch, in_memory_db):
    """Verifies Lidl ticket with discounts and weight-variable products processes correctly."""
    lidl_ticket = {
        "supermarket": "Lidl",
        "date": "2026-05-12",
        "time": "21:06",
        "store": "C/ Vicente Berdusán, 44 (50010, Zaragoza)",
        "source": "Email",
        "total": 8.62,
        "products": [
            _make_product(
                name="Gyozas de verduras", original_name="GYOZAS DE VERDURAS",
                category="Congelados", brand="Lidl",
                original_unit_price=2.49, discount=0.0,
                final_unit_price=2.49, line_total=2.49,
            ),
            _make_product(
                name="Banana", original_name="BANANA",
                category="Frutas", brand=None,
                quantity=0.772, unit="kg",
                original_unit_price=1.49, discount=0.39,
                final_unit_price=1.10, line_total=0.85,
            ),
            _make_product(
                name="Trío de hummus", original_name="TRÍO DE HUMMUS",
                category="Salsas y conservas", brand="Lidl",
                original_unit_price=2.49, discount=0.50,
                final_unit_price=1.99, line_total=1.99,
            ),
        ],
    }

    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "lidl_msg1"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda msg_id: [("lidl.jpg", "image/jpeg", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: lidl_ticket,
    )

    inserted = run_pipeline("subject:(lidl ticket)")
    assert len(inserted) == 1


def test_pipeline_dia_ticket(monkeypatch, in_memory_db):
    """Verifies Dia franchise ticket (with legal entity name) processes correctly."""
    dia_ticket = {
        "supermarket": "Dia",
        "date": "2026-06-23",
        "time": "11:56",
        "store": "Cl. Tomás Bretón, 46 (50005, Zaragoza)",
        "source": "Email",
        "total": 16.22,
        "products": [
            _make_product(
                name="Cuarto trasero de pollo", original_name="CUARTO TRASERO POLLO",
                category="Carnes", brand=None,
                quantity=0.799, unit="kg",
                original_unit_price=2.44, discount=0.0,
                final_unit_price=2.44, line_total=1.95,
            ),
            _make_product(
                name="Crema de cacahuete 100%", original_name="CREMA CACAHUETE 100%",
                category="Salsas y conservas", brand="Dia",
                original_unit_price=3.25, discount=0.0,
                final_unit_price=3.25, line_total=3.25,
            ),
        ],
    }

    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "dia_msg1"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda msg_id: [("dia.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: dia_ticket,
    )

    inserted = run_pipeline("subject:(dia ticket)")
    assert len(inserted) == 1