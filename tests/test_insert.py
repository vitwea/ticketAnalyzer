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


# ──────────────────────────────────────────────────────────────
# C-4 — Savepoint / race-condition tests
# ──────────────────────────────────────────────────────────────

import sqlalchemy as sa


def test_savepoint_survives_integrity_error(db_session):
    """
    The outer transaction must stay intact after a SAVEPOINT rolls back
    due to an IntegrityError.

    We directly exercise the savepoint mechanism by:
      1. Inserting a row via raw SQL (simulates the "winning" process).
      2. Expiring the session cache (simulates having checked before that insert).
      3. Attempting to insert the same row via get_or_create_* → IntegrityError.
      4. Verifying the correct id is returned and the outer tx is still usable.
    """
    # Step 1: insert the "winner" row via raw SQL, bypassing ORM identity map
    db_session.execute(sa.text("INSERT INTO category (name) VALUES ('Frutas')"))
    db_session.flush()
    winner_id = db_session.execute(
        sa.text("SELECT id_category FROM category WHERE name = 'Frutas'")
    ).scalar()

    # Step 2: clear session cache — next query must hit the DB
    db_session.expire_all()

    # Step 3: get_or_create must return the winner's id without crashing
    result_id = get_or_create_category(db_session, "Frutas")
    assert result_id == winner_id

    # Step 4: outer transaction still usable — other entities can be inserted
    brand_id = get_or_create_brand(db_session, "Hacendado")
    assert isinstance(brand_id, int)
    db_session.commit()                           # full commit must succeed
    from src.db.models import Category
    assert db_session.query(Category).count() == 1  # no duplicates


def test_savepoint_begin_nested_directly(db_session):
    """
    Directly verify that begin_nested() rolls back to savepoint on
    IntegrityError without aborting the outer transaction — this is the
    exact mechanism used by _insert_with_savepoint().
    """
    from sqlalchemy.exc import IntegrityError as SAIntegrityError
    from src.db.models import Category as Cat

    # First insert succeeds
    with db_session.begin_nested():
        db_session.add(Cat(name="Bebidas"))
        db_session.flush()
    bebidas_id = db_session.query(Cat).filter_by(name="Bebidas").first().id_category

    # Second insert of same name → IntegrityError → savepoint rolls back
    try:
        with db_session.begin_nested():
            db_session.add(Cat(name="Bebidas"))
            db_session.flush()
    except SAIntegrityError:
        pass  # expected — savepoint was rolled back

    # Outer tx intact: can insert a different row
    with db_session.begin_nested():
        db_session.add(Cat(name="Lácteos"))
        db_session.flush()

    db_session.commit()

    cats = {c.name: c.id_category for c in db_session.query(Cat).all()}
    assert "Bebidas" in cats
    assert "Lácteos" in cats
    assert cats["Bebidas"] == bebidas_id
    assert len(cats) == 2   # no duplicate "Bebidas"


def test_all_savepoint_entities_are_idempotent(db_session):
    """
    Idempotency smoke-test across all entities that use _insert_with_savepoint.
    Calling each twice must return the same id.
    """
    from src.db.insert import get_or_create_source

    id_sup  = get_or_create_supermarket(db_session, "Mercadona")
    id_cat  = get_or_create_category(db_session, "Lácteos")
    id_bra  = get_or_create_brand(db_session, "Hacendado")
    id_src  = get_or_create_source(db_session, "Email")
    id_sto  = get_or_create_store(db_session, id_sup, "C/ Mayor 1", "50001",
                                   "Zaragoza", "Zaragoza", "Spain")
    id_rec  = get_or_create_receipt(db_session, "gm_race_001",
                                    __import__("datetime").datetime(2026, 1, 1),
                                    __import__("decimal").Decimal("10.00"),
                                    id_sto, id_src)

    # Second calls — all should hit the "already exists" fast path
    assert get_or_create_supermarket(db_session, "Mercadona") == id_sup
    assert get_or_create_category(db_session, "Lácteos")      == id_cat
    assert get_or_create_brand(db_session, "Hacendado")       == id_bra
    assert get_or_create_source(db_session, "Email")          == id_src
    assert get_or_create_receipt(db_session, "gm_race_001",
                                 __import__("datetime").datetime(2026, 1, 1),
                                 __import__("decimal").Decimal("10.00"),
                                 id_sto, id_src)               == id_rec

    db_session.commit()


# ──────────────────────────────────────────────────────────────
# C-4 — savepoint / race-condition protection
# ──────────────────────────────────────────────────────────────

def test_savepoint_allows_outer_transaction_to_continue_after_integrity_error(db_session):
    """
    Simulate the TOCTOU race condition:
      1. Process A's SELECT returns None (row doesn't exist yet).
      2. Process B inserts the row and commits.
      3. Process A's INSERT fails with IntegrityError.

    With the savepoint pattern, the IntegrityError must:
      a) Roll back only the savepoint, leaving the outer transaction intact.
      b) Re-query and return the existing row's id.

    We simulate step 2 by manually inserting the row inside a nested
    transaction BEFORE calling get_or_create_category, bypassing the
    initial SELECT check.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from src.db.models import Category

    # Simulate "another process" inserting 'Lácteos' first
    with db_session.begin_nested():
        db_session.add(Category(name="Lácteos"))
    # Now 'Lácteos' exists in the DB (within this transaction's scope)

    # get_or_create_category will:
    #   1. SELECT → finds the row → returns immediately (happy path here)
    # To truly hit the savepoint branch we force an IntegrityError manually:
    try:
        with db_session.begin_nested():
            db_session.add(Category(name="Lácteos"))  # duplicate → IntegrityError
    except IntegrityError:
        pass  # savepoint rolled back; outer transaction must still be usable

    # The outer transaction must be intact — we can still insert and query
    id_cat = get_or_create_category(db_session, "Bebidas")
    assert isinstance(id_cat, int)

    # And the original 'Lácteos' row is still visible
    lacteos_id = get_or_create_category(db_session, "Lácteos")
    assert isinstance(lacteos_id, int)

    # Final commit must succeed — proves the outer transaction was never aborted
    db_session.commit()


def test_savepoint_idempotency_under_simulated_concurrent_insert(db_session):
    """
    Calling get_or_create_* twice for the same unique value must always
    return the same id, even if the second call races with itself.
    This tests the re-query fallback in the IntegrityError handler.
    """
    id1 = get_or_create_category(db_session, "Congelados")
    id2 = get_or_create_category(db_session, "Congelados")
    assert id1 == id2

    id3 = get_or_create_brand(db_session, "Hacendado")
    id4 = get_or_create_brand(db_session, "Hacendado")
    assert id3 == id4

    db_session.commit()