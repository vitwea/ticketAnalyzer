from src.db import connection
from src.db.models import Supermercado, Categoria, Producto, Ticket, LineaTicket
from sqlalchemy.exc import IntegrityError


def insert_supermercado(nombre: str) -> int:
    db = connection.SessionLocal()
    try:
        sup = db.query(Supermercado).filter_by(nombre=nombre).first()
        if sup:
            return sup.id

        sup = Supermercado(nombre=nombre)
        db.add(sup)
        db.commit()
        return sup.id
    finally:
        db.close()


def insert_categoria(nombre: str) -> int:
    db = connection.SessionLocal()
    try:
        cat = db.query(Categoria).filter_by(nombre=nombre).first()
        if cat:
            return cat.id

        cat = Categoria(nombre=nombre)
        db.add(cat)
        db.commit()
        return cat.id
    finally:
        db.close()


def insert_producto(nombre: str, id_categoria: int, unidad_medida: str) -> int:
    db = connection.SessionLocal()
    try:
        prod = (
            db.query(Producto)
            .filter_by(nombre=nombre, id_categoria=id_categoria, unidad_medida=unidad_medida)
            .first()
        )
        if prod:
            return prod.id

        prod = Producto(
            nombre=nombre,
            id_categoria=id_categoria,
            unidad_medida=unidad_medida,
        )
        db.add(prod)
        db.commit()
        return prod.id
    finally:
        db.close()


def insert_ticket(id_supermercado: int, fecha: str, id_mensaje_gmail: str,
                  total: float, tienda: str, hora: str) -> int:
    db = connection.SessionLocal()
    try:
        ticket = db.query(Ticket).filter_by(id_mensaje_gmail=id_mensaje_gmail).first()
        if ticket:
            return ticket.id

        ticket = Ticket(
            id_supermercado=id_supermercado,
            fecha=fecha,
            hora=hora,
            tienda=tienda,
            total=total,
            id_mensaje_gmail=id_mensaje_gmail,
        )
        db.add(ticket)
        db.commit()
        return ticket.id
    finally:
        db.close()


def insert_linea_ticket(
    id_ticket: int,
    id_producto: int,
    cantidad: float,
    unidad_medida: str,
    precio_unitario: float,
    precio_total: float,
    oferta: bool,
    descuento: float,
    tipo_precio: str = "unidad",
) -> int:
    db = connection.SessionLocal()
    try:
        linea = LineaTicket(
            id_ticket=id_ticket,
            id_producto=id_producto,
            cantidad=cantidad,
            unidad_medida=unidad_medida,
            precio_unitario=precio_unitario,
            precio_total=precio_total,
            oferta=oferta,
            descuento=descuento,
            tipo_precio=tipo_precio,
        )
        db.add(linea)
        db.commit()
        return linea.id
    finally:
        db.close()