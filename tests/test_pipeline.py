"""
tests/test_pipeline.py

Integration tests for src/etl/pipeline.py.

The in_memory_db fixture replaces connection.SessionLocal with a factory
bound to a SQLite in-memory engine (StaticPool so all sessions see the same
data).  All Gmail / OCR calls are monkeypatched.
"""

from __future__ import annotations

import pytest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.connection import Base
from src.etl.pipeline import run_pipeline, _validate_ticket_json, _parse_store


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_product(**overrides):
    base = {
        "name": "Pan",
        "original_name": "PAN",
        "category": "Pan",
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


# ──────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────

@pytest.fixture()
def in_memory_db(monkeypatch):
    """
    Patch connection.SessionLocal so all pipeline code uses an in-memory
    SQLite database.  StaticPool ensures all sessions share the same data.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    import src.db.connection as conn_module
    monkeypatch.setattr(conn_module, "SessionLocal", TestSession)

    yield engine
    Base.metadata.drop_all(engine)


# ──────────────────────────────────────────────────────────────
# _validate_ticket_json
# ──────────────────────────────────────────────────────────────

def test_validate_passes_valid_ticket():
    _validate_ticket_json(_make_ticket())


def test_validate_missing_top_level_field():
    for field in ("supermarket", "date", "total", "products"):
        ticket = _make_ticket()
        del ticket[field]
        with pytest.raises(ValueError, match=field):
            _validate_ticket_json(ticket)


def test_validate_missing_product_field():
    required = (
        "name", "category", "quantity", "unit",
        "original_unit_price", "discount", "final_unit_price", "line_total",
    )
    for field in required:
        ticket = _make_ticket(products=[_make_product(**{field: None})])
        with pytest.raises(ValueError, match=field):
            _validate_ticket_json(ticket)


def test_validate_products_not_list():
    with pytest.raises(ValueError, match="list"):
        _validate_ticket_json(_make_ticket(products="not a list"))


# ──────────────────────────────────────────────────────────────
# _parse_store
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("store_str,expected_address,expected_cp,expected_city,expected_province", [
    (
        "Avda. Francisco de Goya, 61 (50005, Zaragoza)",
        "Avda. Francisco de Goya, 61", "50005", "Zaragoza", "Zaragoza",
    ),
    (
        "Pza. Roma, s/n (50010, Zaragoza)",
        "Pza. Roma, s/n", "50010", "Zaragoza", "Zaragoza",
    ),
    (
        "C/ Vicente Berdusán, 44 (50010, Zaragoza)",
        "C/ Vicente Berdusán, 44", "50010", "Zaragoza", "Zaragoza",
    ),
    (
        "Cl. Tomás Bretón, 46 (50005, Zaragoza)",
        "Cl. Tomás Bretón, 46", "50005", "Zaragoza", "Zaragoza",
    ),
    # fallback: no parentheses
    (
        "Avda. Francisco de Goya, 61 50005 Zaragoza",
        "Avda. Francisco de Goya, 61", "50005", "Zaragoza", "Zaragoza",
    ),
])
def test_parse_store_valid(store_str, expected_address, expected_cp, expected_city, expected_province):
    result = _parse_store(store_str)
    assert result is not None
    address, cp, city, province, country = result
    assert address  == expected_address
    assert cp       == expected_cp
    assert city     == expected_city
    assert province == expected_province
    assert country  == "Spain"


def test_parse_store_none_input():
    assert _parse_store(None) is None


def test_parse_store_unparseable():
    assert _parse_store("dirección sin código postal") is None


# ──────────────────────────────────────────────────────────────
# run_pipeline — integration
# ──────────────────────────────────────────────────────────────

def test_pipeline_inserts_receipt(monkeypatch, in_memory_db):
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "msg123"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("ticket.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: _make_ticket(),
    )

    inserted = run_pipeline("from:mercadona")
    assert len(inserted) == 1
    assert isinstance(inserted[0], int)


def test_pipeline_idempotent(monkeypatch, in_memory_db):
    """
    Running the pipeline twice with the same gmail_id must not duplicate receipts.

    First run  → inserts and returns [receipt_id].
    Second run → receipt_exists() fires, message is skipped, returns [].
    The database must contain exactly one Receipt row after both runs.
    """
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "msg123"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("ticket.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: _make_ticket(),
    )

    first  = run_pipeline("from:mercadona")
    second = run_pipeline("from:mercadona")

    assert len(first)  == 1          # inserted on first run
    assert len(second) == 0          # skipped on second run (already exists)

    # Confirm exactly one row in the DB — no duplicates
    from src.db.models import Receipt
    import src.db.connection as conn_module
    db = conn_module.SessionLocal()
    try:
        assert db.query(Receipt).count() == 1
        assert db.query(Receipt).first().gmail_id == "msg123"
    finally:
        db.close()


def test_pipeline_skips_failed_attachment(monkeypatch, in_memory_db):
    """A bad attachment is skipped; the subsequent good message still processes."""
    calls = iter([
        [("bad.pdf",  "application/pdf", b"bad")],
        [("good.pdf", "application/pdf", b"good")],
    ])
    monkeypatch.setattr(
        "src.etl.pipeline.list_messages",
        lambda q: [{"id": "msg_bad"}, {"id": "msg_good"}],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: next(calls),
    )

    def fake_ocr(data, mime):
        if data == b"bad":
            raise ValueError("OCR failed")
        return _make_ticket()

    monkeypatch.setattr("src.etl.pipeline.extract_ticket_data", fake_ocr)

    inserted = run_pipeline("from:mercadona")
    assert len(inserted) == 1


def test_pipeline_transaction_rolls_back_on_bad_product(monkeypatch, in_memory_db):
    """
    If one product in the list raises, the ENTIRE receipt must be rolled back —
    no orphaned receipt row or partial lines in the database.
    """
    from sqlalchemy.orm import sessionmaker as sm
    import src.db.connection as conn_module

    bad_ticket = _make_ticket(products=[
        _make_product(name="Leche entera", category="Lácteos"),
        _make_product(name="", category="Lácteos", quantity=None),  # will fail validation
    ])

    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "bad_msg"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("t.pdf", "application/pdf", b"x")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: bad_ticket,
    )

    inserted = run_pipeline("from:mercadona")
    assert inserted == []

    # Verify no Receipt row was committed
    from src.db.models import Receipt, ReceiptLine
    db = conn_module.SessionLocal()
    try:
        assert db.query(Receipt).count() == 0
        assert db.query(ReceiptLine).count() == 0
    finally:
        db.close()


def test_pipeline_lidl_ticket(monkeypatch, in_memory_db):
    """Lidl ticket with discounts and weight-variable products."""
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
                original_unit_price=2.49, final_unit_price=2.49, line_total=2.49,
            ),
            _make_product(
                name="Banana", original_name="BANANA",
                category="Frutas", brand=None,
                quantity=0.772, unit="kg",
                original_unit_price=1.49, discount=0.39,
                final_unit_price=1.10, line_total=0.85,
            ),
        ],
    }
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "lidl_msg1"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("lidl.jpg", "image/jpeg", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: lidl_ticket,
    )

    assert len(run_pipeline("subject:(lidl ticket)")) == 1


def test_pipeline_dia_ticket(monkeypatch, in_memory_db):
    """Dia ticket with weight-variable products."""
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
                category="Carnes y embutidos", brand=None,
                quantity=0.799, unit="kg",
                original_unit_price=2.44, final_unit_price=2.44, line_total=1.95,
            ),
            _make_product(
                name="Crema de cacahuete 100%", original_name="CREMA CACAHUETE 100%",
                category="Salsas y conservas", brand="Dia",
                original_unit_price=3.25, final_unit_price=3.25, line_total=3.25,
            ),
        ],
    }
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: [{"id": "dia_msg1"}])
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("dia.pdf", "application/pdf", b"fake")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda data, mime: dia_ticket,
    )

    assert len(run_pipeline("subject:(dia ticket)")) == 1


def test_pipeline_reuses_product_via_alias(monkeypatch, in_memory_db):
    """
    M-6: when the same original_name appears in two different tickets,
    the second ticket must reuse the existing Product row via the alias
    table rather than creating a duplicate.

    Scenario:
      Ticket 1 → original_name="LECHE ENTERA" → creates Product(id=1, name="Leche entera")
                  and alias "LECHE ENTERA" → id=1
      Ticket 2 → original_name="LECHE ENTERA" → alias found → reuses Product(id=1)
                  (even though OCR normalized it as "Leche entera 1L" this time)
    After both runs there must be exactly ONE Product row, not two.
    """
    ticket1 = _make_ticket(products=[_make_product(
        name="Leche entera",
        original_name="LECHE ENTERA",
        category="Lácteos",
    )])
    ticket2 = _make_ticket(products=[_make_product(
        name="Leche entera 1L",       # OCR normalized differently
        original_name="LECHE ENTERA", # same original_name as ticket 1
        category="Lácteos",
    )])

    tickets = iter([ticket1, ticket2])

    monkeypatch.setattr(
        "src.etl.pipeline.list_messages",
        lambda q: [{"id": "msg_t1"}, {"id": "msg_t2"}],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.get_attachments_bytes",
        lambda mid: [("t.pdf", "application/pdf", b"x")],
    )
    monkeypatch.setattr(
        "src.etl.pipeline.extract_ticket_data",
        lambda d, m: next(tickets),
    )

    run_pipeline("from:mercadona")

    from src.db.models import Product, ReceiptLine
    import src.db.connection as conn_module

    db = conn_module.SessionLocal()
    try:
        assert db.query(Product).count() == 1, \
            "Expected 1 Product row; alias lookup should have prevented a duplicate"
        assert db.query(ReceiptLine).count() == 2, \
            "Both receipts should have a receipt_line pointing to the same product"
        lines = db.query(ReceiptLine).all()
        assert lines[0].id_product == lines[1].id_product, \
            "Both lines must reference the same product id"
    finally:
        db.close()