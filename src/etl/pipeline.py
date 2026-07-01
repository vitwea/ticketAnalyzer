"""
src/etl/pipeline.py

Each receipt processed by process_ticket_json runs inside a SINGLE
SQLAlchemy transaction:

    open session
    ├── get_or_create_supermarket  (flush)
    ├── get_or_create_source       (flush)
    ├── get_or_create_store        (flush)
    ├── get_or_create_receipt      (flush)
    └── for each product:
        ├── get_or_create_category   (flush)
        ├── get_or_create_brand      (flush)
        ├── get_or_create_product    (flush)
        ├── get_or_create_alias      (flush, if needed)
        └── create_receipt_line      (flush)
    commit  ←── one commit, everything or nothing
    (rollback on any error)
    close session

This guarantees that a receipt is never partially inserted:
either all its lines are in the database or none are.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from src.db import connection
from src.db.insert import (
    create_receipt_line,
    get_or_create_brand,
    get_or_create_category,
    get_or_create_product,
    get_or_create_product_alias,
    get_or_create_receipt,
    get_or_create_source,
    get_or_create_store,
    get_or_create_supermarket,
    receipt_exists,
)
from src.gmail.reader import get_attachments_bytes, list_messages
from src.ocr.unified import extract_ticket_data
from src.config.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────
# Lookup table: first 2 digits of Spanish postal code → province
# ──────────────────────────────────────────────────────────────

_CP_TO_PROVINCE: dict[str, str] = {
    "01": "Álava",        "02": "Albacete",      "03": "Alicante",
    "04": "Almería",      "05": "Ávila",          "06": "Badajoz",
    "07": "Baleares",     "08": "Barcelona",      "09": "Burgos",
    "10": "Cáceres",      "11": "Cádiz",          "12": "Castellón",
    "13": "Ciudad Real",  "14": "Córdoba",         "15": "A Coruña",
    "16": "Cuenca",       "17": "Girona",          "18": "Granada",
    "19": "Guadalajara",  "20": "Gipuzkoa",        "21": "Huelva",
    "22": "Huesca",       "23": "Jaén",            "24": "León",
    "25": "Lleida",       "26": "La Rioja",        "27": "Lugo",
    "28": "Madrid",       "29": "Málaga",          "30": "Murcia",
    "31": "Navarra",      "32": "Ourense",         "33": "Asturias",
    "34": "Palencia",     "35": "Las Palmas",      "36": "Pontevedra",
    "37": "Salamanca",    "38": "S.C. Tenerife",   "39": "Cantabria",
    "40": "Segovia",      "41": "Sevilla",         "42": "Soria",
    "43": "Tarragona",    "44": "Teruel",          "45": "Toledo",
    "46": "Valencia",     "47": "Valladolid",      "48": "Bizkaia",
    "49": "Zamora",       "50": "Zaragoza",        "51": "Ceuta",
    "52": "Melilla",
}


# ──────────────────────────────────────────────────────────────
# Pure helpers (no I/O)
# ──────────────────────────────────────────────────────────────

def _to_decimal(value: object, places: int = 2) -> Decimal:
    """
    Convert any numeric-ish value to a Decimal with fixed precision.
    Using str() as intermediary avoids float representation errors:
        float(1.49) → 1.4899999999999999  (bad)
        Decimal(str(1.49)) → Decimal('1.49')  (correct)
    """
    return Decimal(str(value)).quantize(
        Decimal("0." + "0" * places),
        rounding=ROUND_HALF_UP,
    )


def _validate_ticket_json(ticket_json: dict) -> None:
    """
    Validate the structure returned by the OCR layer.
    Raises ValueError with the name of the first missing field.
    """
    for field in ("supermarket", "date", "total", "products"):
        if field not in ticket_json:
            raise ValueError(f"Missing required field in ticket JSON: '{field}'")

    products = ticket_json["products"]
    if not isinstance(products, list):
        raise ValueError("'products' must be a list")

    required_product_fields = (
        "name", "category", "quantity", "unit",
        "original_unit_price", "discount", "final_unit_price", "line_total",
    )
    for i, p in enumerate(products):
        for field in required_product_fields:
            if field not in p or p[field] is None:
                raise ValueError(f"Product {i} missing required field: '{field}'")


def _parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"Invalid date format: {date_str!r}. Expected YYYY-MM-DD"
        ) from exc


def _parse_store(
    store_str: str | None,
) -> tuple[str, str, str, str, str] | None:
    """
    Parse the OCR store string into (address, postal_code, city, province, country).

    Accepted formats:
        "Avda. Francisco de Goya, 61 (50005, Zaragoza)"  ← canonical
        "Avda. Francisco de Goya, 61 50005 Zaragoza"     ← fallback
    Returns None if parsing fails; never raises.
    """
    if not store_str:
        return None
    try:
        # Strategy 1 — canonical: "address (CP, city)"
        m = re.search(r"^(.*?)\s*\((\d{4,5}),\s*(.+?)\)\s*$", store_str.strip())
        if m:
            address     = m.group(1).strip()
            postal_code = m.group(2).strip()
            city        = m.group(3).strip()
            province    = _CP_TO_PROVINCE.get(postal_code[:2], "Unknown")
            return (address, postal_code, city, province, "Spain")

        # Strategy 2 — fallback: "address CP city"
        m2 = re.search(r"(.+?)\s+(\d{5})\s+(.+)", store_str.strip())
        if m2:
            address     = m2.group(1).strip()
            postal_code = m2.group(2).strip()
            city        = m2.group(3).strip()
            province    = _CP_TO_PROVINCE.get(postal_code[:2], "Unknown")
            return (address, postal_code, city, province, "Spain")

        logger.warning("Could not parse store string: %r", store_str)
        return None
    except Exception as exc:
        logger.warning("Error parsing store string %r: %s", store_str, exc)
        return None


# ──────────────────────────────────────────────────────────────
# Transaction helpers
# ──────────────────────────────────────────────────────────────

def _resolve_store(db, id_supermarket: int, store_str: str | None) -> int:
    """
    Parse and insert the store, falling back to a placeholder if unparseable.
    Always returns a valid id_store.
    """
    if store_str:
        parsed = _parse_store(store_str)
        if parsed:
            address, postal_code, city, province, country = parsed
            return get_or_create_store(
                db, id_supermarket, address, postal_code, city, province, country
            )
    logger.warning("Could not parse store information — using placeholder")
    return get_or_create_store(
        db, id_supermarket, "Unknown", "00000", "Unknown", "Unknown", "Spain"
    )


def _insert_products(db, id_receipt: int, products: list[dict]) -> None:
    """
    Insert all product lines for a receipt within an existing session.
    Any exception propagates immediately so the outer transaction rolls back.
    """
    for i, p in enumerate(products):
        try:
            id_category = get_or_create_category(db, p["category"])

            brand_name = p.get("brand")
            id_brand   = get_or_create_brand(db, brand_name) if brand_name else None

            id_product = get_or_create_product(db, p["name"], id_category, id_brand)

            original_name = p.get("original_name")
            if original_name and original_name != p["name"]:
                get_or_create_product_alias(db, original_name, id_product)

            create_receipt_line(
                db=db,
                id_receipt=id_receipt,
                id_product=id_product,
                quantity=_to_decimal(p["quantity"]),
                unit=p["unit"],
                original_unit_price=_to_decimal(p["original_unit_price"]),
                discount=_to_decimal(p["discount"]),
                final_unit_price=_to_decimal(p["final_unit_price"]),
                line_total=_to_decimal(p["line_total"]),
            )
        except Exception as exc:
            logger.error(
                "Error processing product %d (%r): %s", i, p.get("name"), exc
            )
            raise  # propagate → outer except rolls back the whole transaction


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def process_ticket_json(ticket_json: dict, gmail_msg_id: str) -> int:
    """
    Validate extracted ticket JSON and persist it to the database.

    The entire operation runs in a single transaction: all inserts succeed
    together or roll back together.  This prevents partial receipts
    (e.g. a receipt row with only 3 of 10 product lines) from ever reaching
    the database.

    Returns the id_receipt of the committed receipt.
    Raises on validation errors or database failures after rolling back.
    """
    _validate_ticket_json(ticket_json)

    supermarket_name = ticket_json["supermarket"]
    date_time        = _parse_date(ticket_json["date"])
    store_str        = ticket_json.get("store")
    total            = _to_decimal(ticket_json["total"])
    products         = ticket_json["products"]
    source_name      = ticket_json.get("source", "Email")

    db = connection.SessionLocal()
    try:
        id_supermarket = get_or_create_supermarket(db, supermarket_name)
        id_source      = get_or_create_source(db, source_name)
        id_store       = _resolve_store(db, id_supermarket, store_str)

        id_receipt = get_or_create_receipt(
            db=db,
            gmail_id=gmail_msg_id,
            datetime_val=date_time,
            total_amount=total,
            id_store=id_store,
            id_source=id_source,
        )

        _insert_products(db, id_receipt, products)

        db.commit()
        logger.info(
            "Transaction committed — receipt %d (%s)", id_receipt, gmail_msg_id
        )
        return id_receipt

    except Exception as exc:
        db.rollback()
        logger.error("Transaction rolled back for %s: %s", gmail_msg_id, exc)
        raise
    finally:
        db.close()


def run_pipeline(
    query: str = (
        "from:mercadona "
        "OR subject:(lidl ticket) "
        "OR from:dia.es "
        "OR subject:(alcampo ticket)"
    ),
) -> List[int]:
    """
    Fetch Gmail messages matching the query, run OCR on each attachment,
    and persist the extracted data.  Already-processed messages are skipped
    via receipt_exists().
    """
    logger.info("Running pipeline with query: %s", query)

    msgs = list_messages(query)
    logger.info("Found %d messages.", len(msgs))

    inserted_ids: List[int] = []

    for msg in msgs:
        msg_id = msg["id"]

        if receipt_exists(msg_id):
            logger.info("Skipping %s — already in database.", msg_id)
            continue

        logger.info("Processing message %s", msg_id)

        try:
            attachments = get_attachments_bytes(msg_id)
            for filename, mime, data in attachments:
                try:
                    logger.info("OCR: %s (%s)", filename, mime)
                    ticket_json = extract_ticket_data(data, mime)
                    receipt_id  = process_ticket_json(ticket_json, msg_id)
                    inserted_ids.append(receipt_id)
                    logger.info("Inserted receipt %d", receipt_id)
                except Exception as exc:
                    logger.error("Error processing attachment %s: %s", filename, exc)
                    continue
        except Exception as exc:
            logger.error("Error processing message %s: %s", msg_id, exc)
            continue

    logger.info("Pipeline finished. Inserted %d receipts.", len(inserted_ids))
    return inserted_ids


if __name__ == "__main__":
    run_pipeline()