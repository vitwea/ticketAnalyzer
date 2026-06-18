from __future__ import annotations

from typing import List

from src.gmail.reader import list_messages, get_attachments_bytes
from src.ocr.unified import extract_ticket_data
from src.db.insert import (
    insert_supermercado,
    insert_ticket,
    insert_producto,
    insert_categoria,
    insert_linea_ticket,
)
from src.config.logger import get_logger

logger = get_logger(__name__)


def process_ticket_json(ticket_json: dict, gmail_msg_id: str) -> int:
    supermercado = ticket_json["supermercado"]
    fecha = ticket_json["fecha"]
    hora = ticket_json.get("hora")
    tienda = ticket_json.get("tienda")
    total = ticket_json["total"]
    productos = ticket_json["productos"]

    id_sup = insert_supermercado(supermercado)

    id_ticket = insert_ticket(
        id_supermercado=id_sup,
        fecha=fecha,
        id_mensaje_gmail=gmail_msg_id,
        total=total,
        tienda=tienda,
        hora=hora,
    )

    for p in productos:
        id_cat = insert_categoria(p["categoria"])
        id_prod = insert_producto(p["nombre"], id_cat, p["unidad_medida"])

        insert_linea_ticket(
            id_ticket=id_ticket,
            id_producto=id_prod,
            cantidad=p["cantidad"],
            unidad_medida=p["unidad_medida"],
            precio_unitario=p["precio_unitario"],
            precio_total=p["precio_total"],
            oferta=p["oferta"],
            descuento=p["descuento"],
            tipo_precio=p["tipo_precio"],
        )

    return id_ticket


def run_pipeline(query: str = "from:mercadona") -> List[int]:
    logger.info(f"Running pipeline with query: {query}")

    msgs = list_messages(query)
    logger.info(f"Found {len(msgs)} messages.")

    inserted_ids = []

    for msg in msgs:
        msg_id = msg["id"]
        logger.info(f"Processing Gmail message {msg_id}")

        attachments = get_attachments_bytes(msg_id)

        for filename, mime, data in attachments:
            logger.info(f"OCR processing: {filename} ({mime})")

            ticket_json = extract_ticket_data(data, mime)
            ticket_id = process_ticket_json(ticket_json, msg_id)

            inserted_ids.append(ticket_id)

    logger.info(f"Pipeline finished. Inserted {len(inserted_ids)} tickets.")
    return inserted_ids


if __name__ == "__main__":
    run_pipeline()