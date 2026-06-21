from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Time
from sqlalchemy.orm import relationship
from src.db.connection import Base
from datetime import datetime, timezone


class Supermercado(Base):
    __tablename__ = "supermercado"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)

    tiendas = relationship("Tienda", back_populates="supermercado")
    tickets = relationship("Ticket", back_populates="supermercado")


class Tienda(Base):
    __tablename__ = "tienda"

    id = Column(Integer, primary_key=True)
    supermercado_id = Column(Integer, ForeignKey("supermercado.id"), nullable=False)
    direccion = Column(String, nullable=False)
    codigo_postal = Column(String, nullable=False)
    ciudad = Column(String, nullable=False)

    supermercado = relationship("Supermercado", back_populates="tiendas")
    tickets = relationship("Ticket", back_populates="tienda")


class Ticket(Base):
    __tablename__ = "ticket"

    id = Column(Integer, primary_key=True)
    id_supermercado = Column(Integer, ForeignKey("supermercado.id"), nullable=False)
    tienda_id = Column(Integer, ForeignKey("tienda.id"), nullable=True)
    fecha = Column(DateTime, nullable=False)
    hora = Column(Time, nullable=True)
    total = Column(Float, nullable=False)
    id_mensaje_gmail = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    supermercado = relationship("Supermercado", back_populates="tickets")
    tienda = relationship("Tienda", back_populates="tickets")
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