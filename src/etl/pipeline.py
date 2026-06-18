from __future__ import annotations

from typing import List
from datetime import datetime, time

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


def _validate_ticket_json(ticket_json: dict) -> None:
    """
    Validate that extracted ticket JSON has all required fields.
    Raises ValueError if validation fails.
    """
    required_fields = ["supermercado", "fecha", "total", "productos"]
    for field in required_fields:
        if field not in ticket_json:
            raise ValueError(f"Missing required field in ticket JSON: '{field}'")

    # Validate each product
    productos = ticket_json.get("productos", [])
    if not isinstance(productos, list):
        raise ValueError("'productos' must be a list")

    required_product_fields = [
        "nombre", "categoria", "cantidad", "unidad_medida",
        "precio_unitario", "precio_total", "tipo_precio", "oferta", "descuento"
    ]
    for i, p in enumerate(productos):
        for field in required_product_fields:
            if field not in p or p[field] is None:
                raise ValueError(f"Product {i} missing required field: '{field}'")


def _parse_fecha(fecha_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format to datetime."""
    try:
        return datetime.strptime(fecha_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format: {fecha_str}. Expected YYYY-MM-DD") from e


def _parse_hora(hora_str: str | None) -> time | None:
    """Parse time string in HH:MM or HH:MM:SS format to time."""
    if not hora_str:
        return None
    try:
        # Try HH:MM:SS format first
        return datetime.strptime(hora_str, "%H:%M:%S").time()
    except ValueError:
        try:
            # Fall back to HH:MM format
            return datetime.strptime(hora_str, "%H:%M").time()
        except ValueError as e:
            logger.warning(f"Could not parse time '{hora_str}', ignoring: {e}")
            return None


def process_ticket_json(ticket_json: dict, gmail_msg_id: str) -> int:
    """
    Process extracted ticket JSON and insert into database.
    Validates all required fields before processing.
    """
    _validate_ticket_json(ticket_json)

    supermercado = ticket_json["supermercado"]
    fecha = _parse_fecha(ticket_json["fecha"])
    hora = _parse_hora(ticket_json.get("hora"))
    tienda = ticket_json.get("tienda")
    total = float(ticket_json["total"])
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

    for i, p in enumerate(productos):
        try:
            id_cat = insert_categoria(p["categoria"])
            id_prod = insert_producto(p["nombre"], id_cat, p["unidad_medida"])

            insert_linea_ticket(
                id_ticket=id_ticket,
                id_producto=id_prod,
                cantidad=float(p["cantidad"]),
                unidad_medida=p["unidad_medida"],
                precio_unitario=float(p["precio_unitario"]),
                precio_total=float(p["precio_total"]),
                oferta=bool(p["oferta"]),
                descuento=float(p["descuento"]),
                tipo_precio=p["tipo_precio"],
            )
        except Exception as e:
            logger.error(f"Error inserting product {i} ({p.get('nombre', 'UNKNOWN')}): {e}")
            raise

    return id_ticket


def run_pipeline(query: str = "from:mercadona") -> List[int]:
    logger.info(f"Running pipeline with query: {query}")

    msgs = list_messages(query)
    logger.info(f"Found {len(msgs)} messages.")

    inserted_ids = []

    for msg in msgs:
        msg_id = msg["id"]
        logger.info(f"Processing Gmail message {msg_id}")

        try:
            attachments = get_attachments_bytes(msg_id)

            for filename, mime, data in attachments:
                try:
                    logger.info(f"OCR processing: {filename} ({mime})")

                    ticket_json = extract_ticket_data(data, mime)
                    ticket_id = process_ticket_json(ticket_json, msg_id)

                    inserted_ids.append(ticket_id)
                    logger.info(f"Successfully inserted ticket {ticket_id}")
                except Exception as e:
                    logger.error(f"Error processing attachment {filename}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error processing message {msg_id}: {e}")
            continue

    logger.info(f"Pipeline finished. Inserted {len(inserted_ids)} tickets.")
    return inserted_ids


if __name__ == "__main__":
    run_pipeline()