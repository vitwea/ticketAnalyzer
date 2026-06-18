from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.etl.pipeline import run_pipeline
from src.db.connection import Base


def test_pipeline(monkeypatch):
    # Fake Gmail messages
    fake_msgs = [{"id": "msg123"}]

    # Fake attachment (PDF bytes)
    fake_attachment = [("ticket.pdf", "application/pdf", b"fake")]

    # Fake OCR result (formato completo actualizado)
    fake_ticket_json = {
        "supermercado": "Mercadona",
        "fecha": "2024-06-12",
        "hora": "12:33",
        "tienda": "Zaragoza - Actur",
        "productos": [
            {
                "nombre": "Pan",
                "categoria": "Panadería",
                "cantidad": 1,
                "unidad_medida": "unidad",
                "precio_unitario": 1.0,
                "precio_total": 1.0,
                "tipo_precio": "unidad",
                "oferta": False,
                "descuento": 0.0,
            }
        ],
        "total": 1.0
    }

    # Setup in-memory SQLite DB
    test_engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    # Create tables
    Base.metadata.create_all(test_engine)

    # Patch engine everywhere
    monkeypatch.setattr("src.db.connection.engine", test_engine)
    monkeypatch.setattr("src.db.insert.connection.engine", test_engine)

    # Patch SessionLocal everywhere
    monkeypatch.setattr("src.db.connection.SessionLocal", lambda: TestingSessionLocal())
    monkeypatch.setattr("src.db.insert.connection.SessionLocal", lambda: TestingSessionLocal())

    # Patch Gmail + OCR
    monkeypatch.setattr("src.etl.pipeline.list_messages", lambda q: fake_msgs)
    monkeypatch.setattr("src.etl.pipeline.get_attachments_bytes", lambda msg_id: fake_attachment)
    monkeypatch.setattr("src.etl.pipeline.extract_ticket_data", lambda data, mime: fake_ticket_json)

    # Run pipeline
    inserted = run_pipeline("from:mercadona")

    # Assertions
    assert len(inserted) == 1
    assert isinstance(inserted[0], int)
