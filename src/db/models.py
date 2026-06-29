from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Date, Numeric
from sqlalchemy.orm import relationship
from src.db.connection import Base


class Category(Base):
    __tablename__ = "category"

    id_category = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="category")


class Brand(Base):
    __tablename__ = "brand"

    id_brand = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="brand")


class Product(Base):
    __tablename__ = "product"

    id_product = Column(Integer, primary_key=True)
    normalized_name = Column(String, nullable=False)
    id_category = Column(Integer, ForeignKey("category.id_category"), nullable=False)
    id_brand = Column(Integer, ForeignKey("brand.id_brand"), nullable=True)

    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    aliases = relationship("ProductAlias", back_populates="product")
    receipt_lines = relationship("ReceiptLine", back_populates="product")


class ProductAlias(Base):
    __tablename__ = "product_alias"

    id_alias = Column(Integer, primary_key=True)
    original_name = Column(String, nullable=False)
    id_product = Column(Integer, ForeignKey("product.id_product"), nullable=False)

    product = relationship("Product", back_populates="aliases")


class Supermarket(Base):
    __tablename__ = "supermarket"

    id_supermarket = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    stores = relationship("Store", back_populates="supermarket")


class Store(Base):
    __tablename__ = "store"

    id_store = Column(Integer, primary_key=True)
    id_supermarket = Column(Integer, ForeignKey("supermarket.id_supermarket"), nullable=False)
    address = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    city = Column(String, nullable=False)
    province = Column(String, nullable=False)
    country = Column(String, nullable=False)

    supermarket = relationship("Supermarket", back_populates="stores")
    receipts = relationship("Receipt", back_populates="store")


class Source(Base):
    __tablename__ = "source"

    id_source = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    receipts = relationship("Receipt", back_populates="source")


class Receipt(Base):
    __tablename__ = "receipt"

    id_receipt = Column(Integer, primary_key=True)
    gmail_id = Column(String, unique=True, nullable=False)
    datetime = Column(DateTime, nullable=False)
    total_amount = Column(Numeric, nullable=False)
    id_store = Column(Integer, ForeignKey("store.id_store"), nullable=False)
    id_source = Column(Integer, ForeignKey("source.id_source"), nullable=False)

    store = relationship("Store", back_populates="receipts")
    source = relationship("Source", back_populates="receipts")
    lines = relationship("ReceiptLine", back_populates="receipt")


class ReceiptLine(Base):
    __tablename__ = "receipt_line"

    id_line = Column(Integer, primary_key=True)
    id_receipt = Column(Integer, ForeignKey("receipt.id_receipt"), nullable=False)
    id_product = Column(Integer, ForeignKey("product.id_product"), nullable=False)
    quantity = Column(Numeric, nullable=False)
    unit = Column(String, nullable=False)
    original_unit_price = Column(Numeric, nullable=False)
    discount = Column(Numeric, nullable=False)
    final_unit_price = Column(Numeric, nullable=False)
    line_total = Column(Numeric, nullable=False)

    receipt = relationship("Receipt", back_populates="lines")
    product = relationship("Product", back_populates="receipt_lines")


