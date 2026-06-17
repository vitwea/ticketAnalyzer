from __future__ import annotations

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from src.db.connection import Base


class Supermercado(Base):
    __tablename__ = "supermercado"

    id_supermercado = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)

    tickets = relationship("Ticket", back_populates="supermercado")


class Categoria(Base):
    __tablename__ = "categoria"

    id_categoria = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)

    productos = relationship("Producto", back_populates="categoria")


class Producto(Base):
    __tablename__ = "producto"

    id_producto = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    id_categoria = Column(Integer, ForeignKey("categoria.id_categoria"))
    tipo_precio = Column(String)

    categoria = relationship("Categoria", back_populates="productos")
    lineas = relationship("LineaTicket", back_populates="producto")


class Ticket(Base):
    __tablename__ = "ticket"

    id_ticket = Column(Integer, primary_key=True)
    id_supermercado = Column(Integer, ForeignKey("supermercado.id_supermercado"))
    fecha = Column(String)
    id_mensaje_gmail = Column(String, unique=True)
    total = Column(Float)
    tienda = Column(String)
    hora = Column(String)

    supermercado = relationship("Supermercado", back_populates="tickets")
    lineas = relationship("LineaTicket", back_populates="ticket")


class LineaTicket(Base):
    __tablename__ = "linea_ticket"

    id_linea = Column(Integer, primary_key=True)
    id_ticket = Column(Integer, ForeignKey("ticket.id_ticket"))
    id_producto = Column(Integer, ForeignKey("producto.id_producto"))
    cantidad = Column(Float)
    unidad_medida = Column(String)
    precio_unitario = Column(Float)
    precio_total = Column(Float)
    oferta = Column(Boolean)
    descuento = Column(Float)

    ticket = relationship("Ticket", back_populates="lineas")
    producto = relationship("Producto", back_populates="lineas")
