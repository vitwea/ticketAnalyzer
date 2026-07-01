from __future__ import annotations

from typing import List
from datetime import datetime
import re

from src.gmail.reader import list_messages, get_attachments_bytes
from src.ocr.unified import extract_ticket_data
from src.db.insert import (
    insert_supermarket,
    insert_store,
    insert_receipt,
    insert_product,
    insert_category,
    insert_receipt_line,
    insert_source,
    insert_product_alias,
    insert_brand,
    receipt_exists,
)
from src.config.logger import get_logger

logger = get_logger(__name__)


def _validate_ticket_json(ticket_json: dict) -> None:
    """
    Validate that extracted ticket JSON has all required fields.
    Raises ValueError if validation fails.
    """
    required_fields = ["supermarket", "date", "total", "products"]
    for field in required_fields:
        if field not in ticket_json:
            raise ValueError(f"Missing required field in ticket JSON: '{field}'")

    products = ticket_json.get("products", [])
    if not isinstance(products, list):
        raise ValueError("'products' must be a list")

    required_product_fields = [
        "name", "category", "quantity", "unit",
        "original_unit_price", "discount", "final_unit_price", "line_total"
    ]
    for i, p in enumerate(products):
        for field in required_product_fields:
            if field not in p or p[field] is None:
                raise ValueError(f"Product {i} missing required field: '{field}'")


def _parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format to datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD") from e


def _parse_store(store_str: str | None) -> tuple[str, str, str, str, str] | None:
    """
    Parse store string from OCR into (address, postal_code, city, province, country).

    Accepts the canonical format produced by the OCR prompt:
        "Dirección (CP, Ciudad)"
        e.g. "Avda. Francisco de Goya, 61 (50005, Zaragoza)"
             "Pza. Roma, s/n (50010, Zaragoza)"
             "C/ Vicente Berdusán, 44 (50010, Zaragoza)"
             "Cl. Tomás Bretón, 46 (50005, Zaragoza)"

    Returns None if parsing fails.
    """
    if not store_str:
        return None

    try:
        # Strategy 1: canonical format "address (postal_code, city)"
        m = re.search(r'^(.*?)\s*\((\d{4,5}),\s*(.+?)\)\s*$', store_str.strip())
        if m:
            address     = m.group(1).strip()
            postal_code = m.group(2).strip()
            city        = m.group(3).strip()
            return (address, postal_code, city, "Unknown", "Spain")

        # Strategy 2: fallback — postal code appears without parens
        # e.g. "Avda. Francisco de Goya, 61 50005 Zaragoza"
        m2 = re.search(r'(.+?)\s+(\d{5})\s+(.+)', store_str.strip())
        if m2:
            address     = m2.group(1).strip()
            postal_code = m2.group(2).strip()
            city        = m2.group(3).strip()
            return (address, postal_code, city, "Unknown", "Spain")

        logger.warning(f"Could not parse store string: '{store_str}'")
        return None

    except Exception as e:
        logger.warning(f"Error parsing store string '{store_str}': {e}")
        return None


def process_ticket_json(ticket_json: dict, gmail_msg_id: str) -> int:
    """
    Process extracted ticket JSON and insert into database.
    Validates all required fields before processing.
    """
    _validate_ticket_json(ticket_json)

    supermarket_name = ticket_json["supermarket"]
    date_time        = _parse_date(ticket_json["date"])
    store_str        = ticket_json.get("store")
    total            = float(ticket_json["total"])
    products         = ticket_json["products"]
    source_name      = ticket_json.get("source", "Email")

    id_supermarket = insert_supermarket(supermarket_name)
    id_source      = insert_source(source_name)

    # Parse and insert store
    id_store = None
    if store_str:
        parsed_store = _parse_store(store_str)
        if parsed_store:
            address, postal_code, city, province, country = parsed_store
            id_store = insert_store(id_supermarket, address, postal_code, city, province, country)

    if id_store is None:
        logger.warning("Could not parse store information, using default store")
        id_store = insert_store(id_supermarket, "Unknown", "00000", "Unknown", "Unknown", "Spain")

    id_receipt = insert_receipt(
        gmail_id=gmail_msg_id,
        datetime_val=date_time,
        total_amount=total,
        id_store=id_store,
        id_source=id_source,
    )

    for i, p in enumerate(products):
        try:
            id_category = insert_category(p["category"])

            brand_name = p.get("brand")
            id_brand   = insert_brand(brand_name) if brand_name else None

            id_product = insert_product(p["name"], id_category, id_brand)

            if p.get("original_name") and p["original_name"] != p["name"]:
                insert_product_alias(p["original_name"], id_product)

            insert_receipt_line(
                id_receipt=id_receipt,
                id_product=id_product,
                quantity=float(p["quantity"]),
                unit=p["unit"],
                original_unit_price=float(p["original_unit_price"]),
                discount=float(p["discount"]),
                final_unit_price=float(p["final_unit_price"]),
                line_total=float(p["line_total"]),
            )
        except Exception as e:
            logger.error(f"Error inserting product {i} ({p.get('name', 'UNKNOWN')}): {e}")
            raise

    return id_receipt


def run_pipeline(query: str = (
    'from:mercadona '
    'OR subject:(lidl ticket) '
    'OR from:dia.es '
    'OR subject:(alcampo ticket)'
)) -> List[int]:
    logger.info(f"Running pipeline with query: {query}")

    msgs = list_messages(query)
    logger.info(f"Found {len(msgs)} messages.")

    inserted_ids = []

    for msg in msgs:
        msg_id = msg["id"]

        if receipt_exists(msg_id):
            logger.info(f"Skipping Gmail message {msg_id} — already in database.")
            continue

        logger.info(f"Processing Gmail message {msg_id}")

        try:
            attachments = get_attachments_bytes(msg_id)

            for filename, mime, data in attachments:
                try:
                    logger.info(f"OCR processing: {filename} ({mime})")
                    ticket_json = extract_ticket_data(data, mime)
                    receipt_id  = process_ticket_json(ticket_json, msg_id)
                    inserted_ids.append(receipt_id)
                    logger.info(f"Successfully inserted receipt {receipt_id}")
                except Exception as e:
                    logger.error(f"Error processing attachment {filename}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error processing message {msg_id}: {e}")
            continue

    logger.info(f"Pipeline finished. Inserted {len(inserted_ids)} receipts.")
    return inserted_ids


if __name__ == "__main__":
    run_pipeline()