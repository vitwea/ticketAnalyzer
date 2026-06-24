from sqlalchemy.exc import IntegrityError
from datetime import date
from src.db import connection
from src.db.models import (
    Supermarket, Category, Product, Receipt, ReceiptLine, Store, Brand,
    ProductAlias, Source, PriceHistory
)
from src.config.logger import get_logger

logger = get_logger(__name__)

def receipt_exists(gmail_id: str) -> bool:
    """Return True if a receipt with this Gmail message ID already exists."""
    db = connection.SessionLocal()
    try:
        return db.query(Receipt).filter_by(gmail_id=gmail_id).first() is not None
    finally:
        db.close()


def insert_supermarket(name: str) -> int:
    """Insert or retrieve a supermarket by name."""
    db = connection.SessionLocal()
    try:
        supermarket = db.query(Supermarket).filter_by(name=name).first()
        if supermarket:
            return supermarket.id_supermarket

        supermarket = Supermarket(name=name)
        db.add(supermarket)
        db.commit()
        logger.debug(f"Inserted new supermarket: {name} (id={supermarket.id_supermarket})")
        return supermarket.id_supermarket
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting supermarket {name}: {e}")
        supermarket = db.query(Supermarket).filter_by(name=name).first()
        if supermarket:
            return supermarket.id_supermarket
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting supermarket {name}: {e}")
        raise
    finally:
        db.close()


def insert_store(supermarket_id: int, address: str, postal_code: str,
                 city: str, province: str, country: str) -> int:
    """Insert or retrieve a store location."""
    db = connection.SessionLocal()
    try:
        store = (
            db.query(Store)
            .filter_by(id_supermarket=supermarket_id, address=address, postal_code=postal_code)
            .first()
        )
        if store:
            return store.id_store

        store = Store(
            id_supermarket=supermarket_id,
            address=address,
            postal_code=postal_code,
            city=city,
            province=province,
            country=country,
        )
        db.add(store)
        db.commit()
        logger.debug(f"Inserted new store: {address} (id={store.id_store})")
        return store.id_store
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting store {address}: {e}")
        raise
    finally:
        db.close()


def insert_category(name: str, parent_category_id: int = None) -> int:
    """Insert or retrieve a product category by name."""
    db = connection.SessionLocal()
    try:
        category = db.query(Category).filter_by(name=name).first()
        if category:
            return category.id_category

        category = Category(name=name, parent_category_id=parent_category_id)
        db.add(category)
        db.commit()
        logger.debug(f"Inserted new category: {name} (id={category.id_category})")
        return category.id_category
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting category {name}: {e}")
        category = db.query(Category).filter_by(name=name).first()
        if category:
            return category.id_category
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting category {name}: {e}")
        raise
    finally:
        db.close()


def insert_brand(name: str) -> int:
    """Insert or retrieve a brand by name."""
    db = connection.SessionLocal()
    try:
        brand = db.query(Brand).filter_by(name=name).first()
        if brand:
            return brand.id_brand

        brand = Brand(name=name)
        db.add(brand)
        db.commit()
        logger.debug(f"Inserted new brand: {name} (id={brand.id_brand})")
        return brand.id_brand
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting brand {name}: {e}")
        brand = db.query(Brand).filter_by(name=name).first()
        if brand:
            return brand.id_brand
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting brand {name}: {e}")
        raise
    finally:
        db.close()


def insert_product(normalized_name: str, id_category: int, id_brand: int = None) -> int:
    """Insert or retrieve a product."""
    db = connection.SessionLocal()
    try:
        product = (
            db.query(Product)
            .filter_by(normalized_name=normalized_name, id_category=id_category, id_brand=id_brand)
            .first()
        )
        if product:
            return product.id_product

        product = Product(
            normalized_name=normalized_name,
            id_category=id_category,
            id_brand=id_brand,
        )
        db.add(product)
        db.commit()
        logger.debug(f"Inserted new product: {normalized_name} (id={product.id_product})")
        return product.id_product
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting product {normalized_name}: {e}")
        raise
    finally:
        db.close()


def insert_product_alias(original_name: str, id_product: int) -> int:
    """Insert a product alias."""
    db = connection.SessionLocal()
    try:
        alias = ProductAlias(original_name=original_name, id_product=id_product)
        db.add(alias)
        db.commit()
        logger.debug(f"Inserted product alias: {original_name} (id={alias.id_alias})")
        return alias.id_alias
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting product alias {original_name}: {e}")
        raise
    finally:
        db.close()


def insert_source(name: str) -> int:
    """Insert or retrieve a source by name."""
    db = connection.SessionLocal()
    try:
        source = db.query(Source).filter_by(name=name).first()
        if source:
            return source.id_source

        source = Source(name=name)
        db.add(source)
        db.commit()
        logger.debug(f"Inserted new source: {name} (id={source.id_source})")
        return source.id_source
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting source {name}: {e}")
        raise
    finally:
        db.close()


def insert_receipt(gmail_id: str, datetime_val, total_amount: float,
                   id_store: int, id_source: int) -> int:
    """Insert or retrieve a receipt by Gmail message ID."""
    db = connection.SessionLocal()
    try:
        receipt = db.query(Receipt).filter_by(gmail_id=gmail_id).first()
        if receipt:
            logger.debug(f"Receipt already exists for Gmail message {gmail_id}")
            return receipt.id_receipt

        receipt = Receipt(
            gmail_id=gmail_id,
            datetime=datetime_val,
            total_amount=total_amount,
            id_store=id_store,
            id_source=id_source,
        )
        db.add(receipt)
        db.commit()
        logger.debug(f"Inserted new receipt: {gmail_id} (id={receipt.id_receipt})")
        return receipt.id_receipt
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting receipt {gmail_id}: {e}")
        receipt = db.query(Receipt).filter_by(gmail_id=gmail_id).first()
        if receipt:
            return receipt.id_receipt
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting receipt {gmail_id}: {e}")
        raise
    finally:
        db.close()


def insert_receipt_line(id_receipt: int, id_product: int, quantity: float,
                        unit: str, original_unit_price: float,
                        discount: float, final_unit_price: float,
                        line_total: float) -> int:
    """Insert a receipt line item."""
    db = connection.SessionLocal()
    try:
        line = ReceiptLine(
            id_receipt=id_receipt,
            id_product=id_product,
            quantity=quantity,
            unit=unit,
            original_unit_price=original_unit_price,
            discount=discount,
            final_unit_price=final_unit_price,
            line_total=line_total,
        )
        db.add(line)
        db.commit()
        logger.debug(f"Inserted receipt_line {line.id_line}")
        return line.id_line
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting receipt_line: {e}")
        raise
    finally:
        db.close()


def insert_price_history(id_product: int, id_supermarket: int,
                        price_date: date, price: float) -> int:
    """Insert a price history record."""
    db = connection.SessionLocal()
    try:
        history = PriceHistory(
            id_product=id_product,
            id_supermarket=id_supermarket,
            date=price_date,
            price=price,
        )
        db.add(history)
        db.commit()
        logger.debug(f"Inserted price_history {history.id_history}")
        return history.id_history
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting price_history: {e}")
        raise
    finally:
        db.close()
