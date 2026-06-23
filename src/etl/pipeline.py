from __future__ import annotations

from typing import List
from datetime import datetime

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
    Parse store string from OCR in format: "C/Tenor Gayarre, 4 (50010, Zaragoza)"
    Returns (address, postal_code, city, province, country) or None if parsing fails.
    """
    if not store_str:
        return None

    try:
        if "(" not in store_str or ")" not in store_str:
            logger.warning(f"Store string does not match expected format: {store_str}")
            return None

        open_paren = store_str.rfind("(")
        close_paren = store_str.rfind(")")

        address = store_str[:open_paren].strip()
        paren_content = store_str[open_paren+1:close_paren].strip()

        if "," not in paren_content:
            logger.warning(f"Could not parse postal code and city: {paren_content}")
            return None

        parts = paren_content.split(",", 1)
        postal_code = parts[0].strip()
        city = parts[1].strip()

        # Province and country are not extracted by OCR, use defaults
        province = "Unknown"
        country = "Spain"

        return (address, postal_code, city, province, country)
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
    date_time = _parse_date(ticket_json["date"])
    store_str = ticket_json.get("store")
    total = float(ticket_json["total"])
    products = ticket_json["products"]
    source_name = ticket_json.get("source", "Email")

    # Insert supermarket and source
    id_supermarket = insert_supermarket(supermarket_name)
    id_source = insert_source(source_name)

    # Parse and insert store if available
    id_store = None
    if store_str:
        parsed_store = _parse_store(store_str)
        if parsed_store:
            address, postal_code, city, province, country = parsed_store
            id_store = insert_store(id_supermarket, address, postal_code, city, province, country)

    if id_store is None:
        logger.warning(f"Could not parse store information, using default store")
        id_store = insert_store(id_supermarket, "Unknown", "00000", "Unknown", "Unknown", "Spain")

    # Insert receipt
    id_receipt = insert_receipt(
        gmail_id=gmail_msg_id,
        datetime_val=date_time,
        total_amount=total,
        id_store=id_store,
        id_source=id_source,
    )

    for i, p in enumerate(products):
        try:
            # Insert category and product
            id_category = insert_category(p["category"])

            # Insert brand if OCR identified one for this product
            brand_name = p.get("brand")
            id_brand = insert_brand(brand_name) if brand_name else None

            id_product = insert_product(p["name"], id_category, id_brand)

            # Insert product alias if needed (maps original OCR name to normalized)
            if p.get("original_name") and p["original_name"] != p["name"]:
                insert_product_alias(p["original_name"], id_product)

            # Insert receipt line
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
    'OR subject:(dia ticket) '
    'OR subject:(alcampo ticket)'
)) -> List[int]:
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
                    receipt_id = process_ticket_json(ticket_json, msg_id)

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