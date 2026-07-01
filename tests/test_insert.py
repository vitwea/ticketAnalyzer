"""
tests/test_insert.py

Tests for src/db/insert.py.

All tests receive a fresh in-memory SQLite session via the db_session
fixture.  They call get_or_create_* directly, which is the same API that
pipeline.py uses inside its transaction.

Note: functions no longer open their own sessions, so tests don't need to
monkeypatch connection.SessionLocal — they just pass the fixture session.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.db.connection import Base
from src.db.insert import (
    get_or_create_supermarket,
    get_or_create_store,
    get_or_create_category,
    get_or_create_brand,
    get_or_create_product,
    get_or_create_product_alias,
    get_or_create_source,
    get_or_create_receipt,
    create_receipt_line,
    receipt_exists,
)


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session() -> Session:
    """
    Fresh in-memory SQLite session for each test.
    StaticPool ensures all connections share the same in-memory database,
    which is required for the data written in one session call to be visible
    in the next (SQLite in-memory DBs are connection-scoped by default).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


# ──────────────────────────────────────────────────────────────
# get_or_create_* — idempotency
# ──────────────────────────────────────────────────────────────

def test_supermarket_idempotent(db_session):
    id1 = get_or_create_supermarket(db_session, "Mercadona")
    id2 = get_or_create_supermarket(db_session, "Mercadona")
    assert isinstance(id1, int)
    assert id1 == id2


def test_supermarket_different_names(db_session):
    id1 = get_or_create_supermarket(db_session, "Mercadona")
    id2 = get_or_create_supermarket(db_session, "Lidl")
    assert id1 != id2


def test_category_idempotent(db_session):
    id1 = get_or_create_category(db_session, "Lácteos")
    id2 = get_or_create_category(db_session, "Lácteos")
    assert isinstance(id1, int)
    assert id1 == id2


def test_brand_idempotent(db_session):
    id1 = get_or_create_brand(db_session, "Hacendado")
    id2 = get_or_create_brand(db_session, "Hacendado")
    assert id1 == id2


def test_product_idempotent(db_session):
    id_cat  = get_or_create_category(db_session, "Bebidas")
    id_prod = get_or_create_product(db_session, "Coca-Cola", id_cat)
    assert isinstance(id_prod, int)
    assert get_or_create_product(db_session, "Coca-Cola", id_cat) == id_prod


def test_product_different_brands_create_separate_rows(db_session):
    """Same name + category but different brand → two distinct product rows."""
    id_cat        = get_or_create_category(db_session, "Lácteos")
    id_brand_a    = get_or_create_brand(db_session, "Hacendado")
    id_brand_b    = get_or_create_brand(db_session, "Danone")
    id_prod_a     = get_or_create_product(db_session, "Yogur natural", id_cat, id_brand_a)
    id_prod_b     = get_or_create_product(db_session, "Yogur natural", id_cat, id_brand_b)
    assert id_prod_a != id_prod_b


def test_product_alias_idempotent(db_session):
    id_cat   = get_or_create_category(db_session, "Frutas")
    id_prod  = get_or_create_product(db_session, "Tomate pera", id_cat)
    id_alias = get_or_create_product_alias(db_session, "PLT TOM 1KG", id_prod)
    assert isinstance(id_alias, int)
    assert get_or_create_product_alias(db_session, "PLT TOM 1KG", id_prod) == id_alias


def test_source_idempotent(db_session):
    id1 = get_or_create_source(db_session, "Email")
    id2 = get_or_create_source(db_session, "Email")
    assert id1 == id2


# ──────────────────────────────────────────────────────────────
# get_or_create_receipt — idempotency
# ──────────────────────────────────────────────────────────────

def _make_store(db_session) -> tuple[int, int]:
    """Helper: return (id_supermarket, id_store) for test receipts."""
    id_sup   = get_or_create_supermarket(db_session, "Carrefour")
    id_store = get_or_create_store(
        db_session, id_sup, "Calle Mayor, 1", "50001", "Zaragoza", "Zaragoza", "Spain"
    )
    return id_sup, id_store


def test_receipt_idempotent(db_session):
    _, id_store  = _make_store(db_session)
    id_source    = get_or_create_source(db_session, "Email")

    kwargs = dict(
        gmail_id="abc123",
        datetime_val=datetime(2024, 1, 1, 12, 30),
        total_amount=Decimal("12.50"),
        id_store=id_store,
        id_source=id_source,
    )
    id1 = get_or_create_receipt(db_session, **kwargs)
    id2 = get_or_create_receipt(db_session, **kwargs)
    assert isinstance(id1, int)
    assert id1 == id2


# ──────────────────────────────────────────────────────────────
# create_receipt_line
# ──────────────────────────────────────────────────────────────

def test_create_receipt_line_no_error(db_session):
    _, id_store = _make_store(db_session)
    id_source   = get_or_create_source(db_session, "Email")
    id_cat      = get_or_create_category(db_session, "Snacks")
    id_prod     = get_or_create_product(db_session, "Patatas", id_cat)
    id_rcpt     = get_or_create_receipt(
        db_session, "xyz789", datetime(2024, 1, 1, 10, 0),
        Decimal("3.20"), id_store, id_source,
    )

    create_receipt_line(
        db_session,
        id_receipt=id_rcpt,
        id_product=id_prod,
        quantity=Decimal("2"),
        unit="unidad",
        original_unit_price=Decimal("1.00"),
        discount=Decimal("0.00"),
        final_unit_price=Decimal("1.00"),
        line_total=Decimal("2.00"),
    )
    db_session.commit()  # must not raise


def test_create_receipt_line_decimal_precision(db_session):
    """Verify that float-derived values are stored with correct precision."""
    _, id_store = _make_store(db_session)
    id_source   = get_or_create_source(db_session, "Email")
    id_cat      = get_or_create_category(db_session, "Frutas")
    id_prod     = get_or_create_product(db_session, "Banana", id_cat)
    id_rcpt     = get_or_create_receipt(
        db_session, "banana_msg", datetime(2024, 6, 1),
        Decimal("0.85"), id_store, id_source,
    )

    create_receipt_line(
        db_session,
        id_receipt=id_rcpt,
        id_product=id_prod,
        quantity=Decimal("0.772"),
        unit="kg",
        original_unit_price=Decimal("1.49"),
        discount=Decimal("0.39"),
        final_unit_price=Decimal("1.10"),
        line_total=Decimal("0.85"),
    )
    db_session.commit()

    from src.db.models import ReceiptLine
    line = db_session.query(ReceiptLine).filter_by(id_receipt=id_rcpt).first()
    assert line is not None
    assert float(line.discount) == pytest.approx(0.39)
    assert float(line.final_unit_price) == pytest.approx(1.10)


# ──────────────────────────────────────────────────────────────
# receipt_exists — standalone session
# ──────────────────────────────────────────────────────────────

def test_receipt_exists_false(monkeypatch):
    """receipt_exists must return False for an unknown gmail_id."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)

    import src.db.connection as conn_module
    monkeypatch.setattr(conn_module, "SessionLocal", Sess)

    assert receipt_exists("nonexistent_id") is False


def test_receipt_exists_true(monkeypatch):
    """receipt_exists must return True after a receipt has been committed."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    import src.db.connection as conn_module
    monkeypatch.setattr(conn_module, "SessionLocal", Sess)

    # Insert a receipt via the shared session API and commit it
    db = Sess()
    try:
        id_sup   = get_or_create_supermarket(db, "Dia")
        id_store = get_or_create_store(db, id_sup, "C/ Mayor", "28001", "Madrid", "Madrid", "Spain")
        id_src   = get_or_create_source(db, "Email")
        get_or_create_receipt(db, "exists_id", datetime(2024, 1, 1), Decimal("5.00"), id_store, id_src)
        db.commit()
    finally:
        db.close()

    assert receipt_exists("exists_id") is True
    assert receipt_exists("other_id") is False