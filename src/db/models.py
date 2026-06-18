from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Time
from sqlalchemy.orm import relationship
from src.db.connection import Base
from datetime import datetime, timezone


class Supermercado(Base):
    __tablename__ = "supermercado"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)

    tickets = relationship("Ticket", back_populates="supermercado")


class Ticket(Base):
    __tablename__ = "ticket"

    id = Column(Integer, primary_key=True)
    id_supermercado = Column(Integer, ForeignKey("supermercado.id"), nullable=False)
    fecha = Column(DateTime, nullable=False)
    hora = Column(Time, nullable=True)
    tienda = Column(String, nullable=True)
    total = Column(Float, nullable=False)
    id_mensaje_gmail = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    supermercado = relationship("Supermercado", back_populates="tickets")
    lineas = relationship("LineaTicket", back_populates="ticket")


class Categoria(Base):
    __tablename__ = "categoria"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)

    productos = relationship("Producto", back_populates="categoria")


class Producto(Base):
    __tablename__ = "producto"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    id_categoria = Column(Integer, ForeignKey("categoria.id"), nullable=False)
    unidad_medida = Column(String, nullable=False)

    categoria = relationship("Categoria", back_populates="productos")
    lineas = relationship("LineaTicket", back_populates="producto")


class LineaTicket(Base):
    __tablename__ = "linea_ticket"

    id = Column(Integer, primary_key=True)
    id_ticket = Column(Integer, ForeignKey("ticket.id"), nullable=False)
    id_producto = Column(Integer, ForeignKey("producto.id"), nullable=False)

    cantidad = Column(Float, nullable=False)
    unidad_medida = Column(String, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    precio_total = Column(Float, nullable=False)

    tipo_precio = Column(String, nullable=False)  # "unidad" | "peso"
    oferta = Column(Boolean, default=False)
    descuento = Column(Float, default=0.0)

    ticket = relationship("Ticket", back_populates="lineas")
    producto = relationship("Producto", back_populates="lineas")