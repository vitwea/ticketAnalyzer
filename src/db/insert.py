"""
src/db/insert.py

All public functions follow the same contract:

    get_or_create_*(db: Session, ...) -> int

They accept an *external* SQLAlchemy session, use db.flush() (not commit),
and never close the session.  The caller owns the transaction lifecycle:

    db = connection.SessionLocal()
    try:
        id_a = get_or_create_supermarket(db, "Mercadona")
        id_b = get_or_create_category(db, "Lácteos")
        ...
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

The sole exception is receipt_exists(), which is a read-only pre-flight
check called *before* any transaction is opened and therefore manages its
own short-lived session.
"""

from __future__ import annotations

from decimal import Decimal

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


# ──────────────────────────────────────────────────────────────
# Stand-alone helper (own session — read-only)
# ──────────────────────────────────────────────────────────────

def receipt_exists(gmail_id: str) -> bool:
    """Return True if a receipt with this Gmail message ID already exists."""
    db = connection.SessionLocal()
    try:
        return db.query(Receipt).filter_by(gmail_id=gmail_id).first() is not None
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────
# Session-injection helpers  (flush, no commit)
# ──────────────────────────────────────────────────────────────

def get_or_create_supermarket(db: Session, name: str) -> int:
    """Get or create a supermarket by name."""
    obj = db.query(Supermarket).filter_by(name=name).first()
    if obj:
        return obj.id_supermarket
    obj = Supermarket(name=name)
    db.add(obj)
    db.flush()
    logger.debug("New supermarket: %s (id=%d)", name, obj.id_supermarket)
    return obj.id_supermarket


def get_or_create_store(
    db: Session,
    id_supermarket: int,
    address: str,
    postal_code: str,
    city: str,
    province: str,
    country: str,
) -> int:
    """Get or create a store, keyed on (supermarket, address, postal_code)."""
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


def get_or_create_category(db: Session, name: str) -> int:
    """Get or create a product category by name."""
    obj = db.query(Category).filter_by(name=name).first()
    if obj:
        return obj.id_category
    obj = Category(name=name)
    db.add(obj)
    db.flush()
    logger.debug("New category: %s (id=%d)", name, obj.id_category)
    return obj.id_category


def get_or_create_brand(db: Session, name: str) -> int:
    """Get or create a brand by name."""
    obj = db.query(Brand).filter_by(name=name).first()
    if obj:
        return obj.id_brand
    obj = Brand(name=name)
    db.add(obj)
    db.flush()
    logger.debug("New brand: %s (id=%d)", name, obj.id_brand)
    return obj.id_brand


def get_or_create_product(
    db: Session,
    normalized_name: str,
    id_category: int,
    id_brand: int | None = None,
) -> int:
    """Get or create a normalized product, keyed on (name, category, brand)."""
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
    """Get or create a product alias, keyed on (original_name, product)."""
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


def get_or_create_source(db: Session, name: str) -> int:
    """Get or create a receipt source by name."""
    obj = db.query(Source).filter_by(name=name).first()
    if obj:
        return obj.id_source
    obj = Source(name=name)
    db.add(obj)
    db.flush()
    logger.debug("New source: %s (id=%d)", name, obj.id_source)
    return obj.id_source


def get_or_create_receipt(
    db: Session,
    gmail_id: str,
    datetime_val,
    total_amount: Decimal,
    id_store: int,
    id_source: int,
) -> int:
    """
    Get or create a receipt, keyed on gmail_id (unique constraint).
    Returns the existing id without error if already present — this covers
    the unlikely race where receipt_exists() passed but another process
    committed the same receipt before us.
    """
    obj = db.query(Receipt).filter_by(gmail_id=gmail_id).first()
    if obj:
        logger.debug("Receipt already exists: %s", gmail_id)
        return obj.id_receipt
    obj = Receipt(
        gmail_id=gmail_id,
        datetime=datetime_val,
        total_amount=total_amount,
        id_store=id_store,
        id_source=id_source,
    )
    db.add(obj)
    db.flush()
    logger.debug("New receipt: %s (id=%d)", gmail_id, obj.id_receipt)
    return obj.id_receipt


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
    """
    Insert a receipt line item.

    No idempotency check here: the caller is responsible for ensuring the
    enclosing transaction is atomic (i.e. either all lines are inserted or
    the whole transaction is rolled back).  Duplicate lines from a retry of
    the same gmail_id are prevented by the receipt_exists() guard in
    run_pipeline(), which skips already-processed messages before any
    transaction is opened.
    """
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