"""
src/db/insert.py

All public functions follow the session-injection contract:

    get_or_create_*(db: Session, ...) -> int

They accept an external SQLAlchemy session, use db.flush() (not commit),
and never close the session.  The caller owns the transaction lifecycle.

Race-condition safety (C-4):
  Functions that insert rows protected by a UNIQUE constraint use a
  SAVEPOINT (db.begin_nested()) to handle the TOCTOU window between the
  initial SELECT and the INSERT.  If another process inserts the same row
  between our SELECT and INSERT, the IntegrityError rolls back only the
  savepoint — the outer transaction remains intact and we re-query to
  return the existing row.

  Affected functions (those with unique constraints):
    get_or_create_supermarket  (Supermarket.name UNIQUE)
    get_or_create_category     (Category.name UNIQUE)
    get_or_create_brand        (Brand.name UNIQUE)
    get_or_create_source       (Source.name UNIQUE)
    get_or_create_receipt      (Receipt.gmail_id UNIQUE)

  NOT affected (no unique constraint → no IntegrityError risk):
    get_or_create_store, get_or_create_product,
    get_or_create_product_alias, create_receipt_line
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import connection
from src.db.models import (
    Brand,
    Category,
    Product,
    ProductAlias,
    Receipt,
    ReceiptLine,
    Source,
    Store,
    Supermarket,
)
from src.config.logger import get_logger

logger = get_logger(__name__)


# ── Stand-alone helper (own session — read-only) ──────────────────────────────

def receipt_exists(gmail_id: str) -> bool:
    """Return True if a receipt with this Gmail message ID already exists."""
    db = connection.SessionLocal()
    try:
        return db.query(Receipt).filter_by(gmail_id=gmail_id).first() is not None
    finally:
        db.close()


def get_product_id_for_alias(db: Session, original_name: str) -> int | None:
    """
    Return the product id already mapped to this original_name, or None.

    Called by _insert_products before creating a new Product row (M-6).
    If the alias exists the caller reuses the mapped product, preventing
    duplicate Product rows when OCR normalizes the same receipt line
    differently across two tickets but produces the same original_name.

    Example:
      Ticket 1 -> original_name="LECHE ENTERA" -> Product(id=1, name="Leche entera")
      Ticket 2 -> original_name="LECHE ENTERA" -> alias found -> reuse id=1
                  (even if OCR would have normalized it as "Leche entera 1L")
    """
    obj = db.query(ProductAlias).filter_by(original_name=original_name).first()
    return obj.id_product if obj else None


# ── Session-injection helpers with savepoint protection ───────────────────────

def get_or_create_supermarket(db: Session, name: str) -> int:
    """Get or create a supermarket by name (UNIQUE constraint → savepoint)."""
    obj = db.query(Supermarket).filter_by(name=name).first()
    if obj:
        return obj.id_supermarket
    try:
        with db.begin_nested():
            obj = Supermarket(name=name)
            db.add(obj)
        logger.debug("New supermarket: %s (id=%d)", name, obj.id_supermarket)
        return obj.id_supermarket
    except IntegrityError:
        logger.debug("Supermarket '%s' inserted concurrently — fetching row", name)
        return db.query(Supermarket).filter_by(name=name).first().id_supermarket


def get_or_create_category(db: Session, name: str) -> int:
    """Get or create a product category (UNIQUE constraint → savepoint)."""
    obj = db.query(Category).filter_by(name=name).first()
    if obj:
        return obj.id_category
    try:
        with db.begin_nested():
            obj = Category(name=name)
            db.add(obj)
        logger.debug("New category: %s (id=%d)", name, obj.id_category)
        return obj.id_category
    except IntegrityError:
        logger.debug("Category '%s' inserted concurrently — fetching row", name)
        return db.query(Category).filter_by(name=name).first().id_category


def get_or_create_brand(db: Session, name: str) -> int:
    """Get or create a brand (UNIQUE constraint → savepoint)."""
    obj = db.query(Brand).filter_by(name=name).first()
    if obj:
        return obj.id_brand
    try:
        with db.begin_nested():
            obj = Brand(name=name)
            db.add(obj)
        logger.debug("New brand: %s (id=%d)", name, obj.id_brand)
        return obj.id_brand
    except IntegrityError:
        logger.debug("Brand '%s' inserted concurrently — fetching row", name)
        return db.query(Brand).filter_by(name=name).first().id_brand


def get_or_create_store(
    db: Session,
    id_supermarket: int,
    address: str,
    postal_code: str,
    city: str,
    province: str,
    country: str,
) -> int:
    """Get or create a store, keyed on (supermarket, address, postal_code).
    No unique constraint → no savepoint needed."""
    obj = (
        db.query(Store)
        .filter_by(
            id_supermarket=id_supermarket,
            address=address,
            postal_code=postal_code,
        )
        .first()
    )
    if obj:
        return obj.id_store
    obj = Store(
        id_supermarket=id_supermarket,
        address=address,
        postal_code=postal_code,
        city=city,
        province=province,
        country=country,
    )
    db.add(obj)
    db.flush()
    logger.debug("New store: %s (id=%d)", address, obj.id_store)
    return obj.id_store


def get_or_create_source(db: Session, name: str) -> int:
    """Get or create a receipt source (UNIQUE constraint → savepoint)."""
    obj = db.query(Source).filter_by(name=name).first()
    if obj:
        return obj.id_source
    try:
        with db.begin_nested():
            obj = Source(name=name)
            db.add(obj)
        logger.debug("New source: %s (id=%d)", name, obj.id_source)
        return obj.id_source
    except IntegrityError:
        logger.debug("Source '%s' inserted concurrently — fetching row", name)
        return db.query(Source).filter_by(name=name).first().id_source


def get_or_create_product(
    db: Session,
    normalized_name: str,
    id_category: int,
    id_brand: int | None = None,
) -> int:
    """Get or create a normalized product, keyed on (name, category, brand).
    No unique constraint → no savepoint needed."""
    obj = (
        db.query(Product)
        .filter_by(
            normalized_name=normalized_name,
            id_category=id_category,
            id_brand=id_brand,
        )
        .first()
    )
    if obj:
        return obj.id_product
    obj = Product(
        normalized_name=normalized_name,
        id_category=id_category,
        id_brand=id_brand,
    )
    db.add(obj)
    db.flush()
    logger.debug("New product: %s (id=%d)", normalized_name, obj.id_product)
    return obj.id_product


def get_or_create_product_alias(
    db: Session,
    original_name: str,
    id_product: int,
) -> int:
    """Get or create a product alias, keyed on (original_name, product).
    No unique constraint → no savepoint needed."""
    obj = db.query(ProductAlias).filter_by(
        original_name=original_name,
        id_product=id_product,
    ).first()
    if obj:
        return obj.id_alias
    obj = ProductAlias(original_name=original_name, id_product=id_product)
    db.add(obj)
    db.flush()
    logger.debug("New alias: %s (id=%d)", original_name, obj.id_alias)
    return obj.id_alias


def get_or_create_receipt(
    db: Session,
    gmail_id: str,
    datetime_val,
    total_amount: Decimal,
    id_store: int,
    id_source: int,
) -> int:
    """Get or create a receipt by gmail_id (UNIQUE constraint → savepoint)."""
    obj = db.query(Receipt).filter_by(gmail_id=gmail_id).first()
    if obj:
        logger.debug("Receipt already exists: %s", gmail_id)
        return obj.id_receipt
    try:
        with db.begin_nested():
            obj = Receipt(
                gmail_id=gmail_id,
                purchased_at=datetime_val,
                total_amount=total_amount,
                id_store=id_store,
                id_source=id_source,
            )
            db.add(obj)
        logger.debug("New receipt: %s (id=%d)", gmail_id, obj.id_receipt)
        return obj.id_receipt
    except IntegrityError:
        logger.debug("Receipt '%s' inserted concurrently — fetching row", gmail_id)
        return db.query(Receipt).filter_by(gmail_id=gmail_id).first().id_receipt


def create_receipt_line(
    db: Session,
    id_receipt: int,
    id_product: int,
    quantity: Decimal,
    unit: str,
    original_unit_price: Decimal,
    discount: Decimal,
    final_unit_price: Decimal,
    line_total: Decimal,
) -> None:
    """Insert a receipt line item.
    No idempotency check — caller owns the atomic transaction."""
    obj = ReceiptLine(
        id_receipt=id_receipt,
        id_product=id_product,
        quantity=quantity,
        unit=unit,
        original_unit_price=original_unit_price,
        discount=discount,
        final_unit_price=final_unit_price,
        line_total=line_total,
    )
    db.add(obj)
    db.flush()
    logger.debug(
        "New receipt_line (receipt=%d, product=%d)", id_receipt, id_product
    )