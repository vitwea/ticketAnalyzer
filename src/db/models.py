"""
src/db/models.py

ORM models for ticketAnalyzer.

Index strategy:
  - Primary keys: implicit B-tree index (all databases).
  - Unique constraints (gmail_id, category.name, brand.name, supermarket.name):
    implicit unique index — no explicit Index needed.
  - Composite lookup index on Product: (normalized_name, id_category, id_brand)
    — this is the key used by get_or_create_product on every receipt line.
  - Lookup index on ProductAlias.original_name
    — used by review_aliases and future alias-dedup logic.
  - Lookup index on ReceiptLine.id_receipt
    — used by every JOIN that assembles a receipt's lines.
"""

from sqlalchemy import Column, Index, Integer, String, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import relationship
from src.db.connection import Base


class Category(Base):
    __tablename__ = "category"

    id_category = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category id={self.id_category} name={self.name!r}>"


class Brand(Base):
    __tablename__ = "brand"

    id_brand = Column(Integer, primary_key=True)
    name     = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="brand")

    def __repr__(self) -> str:
        return f"<Brand id={self.id_brand} name={self.name!r}>"


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        # Composite index used by get_or_create_product on every receipt line.
        # (normalized_name, id_category, id_brand) is the natural key.
        Index("ix_product_name_cat_brand", "normalized_name", "id_category", "id_brand"),
    )

    id_product      = Column(Integer, primary_key=True)
    normalized_name = Column(String, nullable=False)
    id_category     = Column(Integer, ForeignKey("category.id_category"), nullable=False)
    id_brand        = Column(Integer, ForeignKey("brand.id_brand"), nullable=True)

    category      = relationship("Category", back_populates="products")
    brand         = relationship("Brand", back_populates="products")
    aliases       = relationship("ProductAlias", back_populates="product")
    receipt_lines = relationship("ReceiptLine", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product id={self.id_product} name={self.normalized_name!r}>"


class ProductAlias(Base):
    __tablename__ = "product_alias"
    __table_args__ = (
        # Used by review_aliases (full scan) and future alias-lookup logic.
        Index("ix_alias_original_name", "original_name"),
    )

    id_alias      = Column(Integer, primary_key=True)
    original_name = Column(String, nullable=False)
    id_product    = Column(Integer, ForeignKey("product.id_product"), nullable=False)

    product = relationship("Product", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<ProductAlias id={self.id_alias} original={self.original_name!r}>"


class Supermarket(Base):
    __tablename__ = "supermarket"

    id_supermarket = Column(Integer, primary_key=True)
    name           = Column(String, unique=True, nullable=False)

    stores = relationship("Store", back_populates="supermarket")

    def __repr__(self) -> str:
        return f"<Supermarket id={self.id_supermarket} name={self.name!r}>"


class Store(Base):
    __tablename__ = "store"

    id_store       = Column(Integer, primary_key=True)
    id_supermarket = Column(Integer, ForeignKey("supermarket.id_supermarket"), nullable=False)
    address        = Column(String, nullable=False)
    postal_code    = Column(String, nullable=False)
    city           = Column(String, nullable=False)
    province       = Column(String, nullable=False)
    country        = Column(String, nullable=False)

    supermarket = relationship("Supermarket", back_populates="stores")
    receipts    = relationship("Receipt", back_populates="store")

    def __repr__(self) -> str:
        return f"<Store id={self.id_store} address={self.address!r}>"


class Source(Base):
    __tablename__ = "source"

    id_source = Column(Integer, primary_key=True)
    name      = Column(String, nullable=False)

    receipts = relationship("Receipt", back_populates="source")

    def __repr__(self) -> str:
        return f"<Source id={self.id_source} name={self.name!r}>"


class Receipt(Base):
    __tablename__ = "receipt"
    # gmail_id has unique=True → implicit unique index; no extra Index needed.

    id_receipt   = Column(Integer, primary_key=True)
    gmail_id     = Column(String, unique=True, nullable=False)
    # Column renamed from 'datetime' to 'purchased_at' to avoid shadowing
    # the Python datetime type in the same namespace (M-3).
    purchased_at = Column(DateTime, nullable=False)
    total_amount = Column(Numeric, nullable=False)
    id_store     = Column(Integer, ForeignKey("store.id_store"), nullable=False)
    id_source    = Column(Integer, ForeignKey("source.id_source"), nullable=False)

    store  = relationship("Store", back_populates="receipts")
    source = relationship("Source", back_populates="receipts")
    lines  = relationship("ReceiptLine", back_populates="receipt")

    def __repr__(self) -> str:
        return f"<Receipt id={self.id_receipt} gmail_id={self.gmail_id!r}>"


class ReceiptLine(Base):
    __tablename__ = "receipt_line"
    __table_args__ = (
        # Every query that assembles a receipt's lines filters by id_receipt.
        Index("ix_receipt_line_receipt", "id_receipt"),
    )

    id_line             = Column(Integer, primary_key=True)
    id_receipt          = Column(Integer, ForeignKey("receipt.id_receipt"), nullable=False)
    id_product          = Column(Integer, ForeignKey("product.id_product"), nullable=False)
    quantity            = Column(Numeric, nullable=False)
    unit                = Column(String, nullable=False)
    original_unit_price = Column(Numeric, nullable=False)
    discount            = Column(Numeric, nullable=False)
    final_unit_price    = Column(Numeric, nullable=False)
    line_total          = Column(Numeric, nullable=False)

    receipt = relationship("Receipt", back_populates="lines")
    product = relationship("Product", back_populates="receipt_lines")

    def __repr__(self) -> str:
        return (
            f"<ReceiptLine id={self.id_line} "
            f"receipt={self.id_receipt} product={self.id_product}>"
        )