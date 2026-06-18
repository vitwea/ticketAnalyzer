import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.connection import Base
from src.db.insert import (
    insert_supermercado,
    insert_categoria,
    insert_producto,
    insert_ticket,
    insert_linea_ticket,
)


@pytest.fixture(scope="function", autouse=True)
def setup_test_db(monkeypatch):
    """
    Creates a fresh in-memory SQLite database for each test.
    Overrides the global engine and session factory.
    """
    test_engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    # Create tables
    Base.metadata.create_all(test_engine)

    # Patch engine + session factory
    monkeypatch.setattr("src.db.connection.engine", test_engine)
    monkeypatch.setattr("src.db.connection.SessionLocal", TestingSessionLocal)

    yield  # run the test

    # Drop tables after test
    Base.metadata.drop_all(test_engine)


def test_insert_supermercado():
    id1 = insert_supermercado("Mercadona")
    id2 = insert_supermercado("Mercadona")  # no dup

    assert id1 == id2
    assert isinstance(id1, int)


def test_insert_categoria():
    id1 = insert_categoria("Lácteos")
    id2 = insert_categoria("Lácteos")

    assert id1 == id2
    assert isinstance(id1, int)


def test_insert_producto():
    id_cat = insert_categoria("Bebidas")
    id_prod = insert_producto("Coca-Cola", id_cat, "unidad")

    assert isinstance(id_prod, int)


def test_insert_ticket():
    id_sup = insert_supermercado("Carrefour")

    id_ticket = insert_ticket(
        id_supermercado=id_sup,
        fecha="2024-01-01",
        id_mensaje_gmail="abc123",
        total=12.50,
        tienda="Carrefour Actur",
        hora="12:30",
    )

    assert isinstance(id_ticket, int)

    # No dup
    id_ticket2 = insert_ticket(
        id_supermercado=id_sup,
        fecha="2024-01-01",
        id_mensaje_gmail="abc123",
        total=12.50,
        tienda="Carrefour Actur",
        hora="12:30",
    )

    assert id_ticket == id_ticket2


def test_insert_linea_ticket():
    id_sup = insert_supermercado("Dia")
    id_cat = insert_categoria("Snacks")
    id_prod = insert_producto("Patatas", id_cat, "unidad")

    id_ticket = insert_ticket(
        id_supermercado=id_sup,
        fecha="2024-01-01",
        id_mensaje_gmail="xyz789",
        total=3.20,
        tienda="Dia Centro",
        hora="10:00",
    )

    insert_linea_ticket(
        id_ticket=id_ticket,
        id_producto=id_prod,
        cantidad=2,
        unidad_medida="uds",
        precio_unitario=1.00,
        precio_total=2.00,
        oferta=False,
        descuento=0.0,
    )

    # If no exception → OK
    assert True
