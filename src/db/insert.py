from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.connection import get_session
from src.db.models import (
    Supermercado,
    Categoria,
    Producto,
    Ticket,
    LineaTicket,
)


def get_or_create(session, model, defaults=None, **kwargs):
    instance = session.execute(
        select(model).filter_by(**kwargs)
    ).scalar_one_or_none()

    if instance:
        return instance

    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        instance = session.execute(
            select(model).filter_by(**kwargs)
        ).scalar_one_or_none()

    return instance


def insert_supermercado(nombre: str) -> int:
    with get_session() as session:
        supermercado = get_or_create(session, Supermercado, nombre=nombre)
        return supermercado.id_supermercado


def insert_categoria(nombre: str) -> int:
    with get_session() as session:
        categoria = get_or_create(session, Categoria, nombre=nombre)
        return categoria.id_categoria


def insert_producto(nombre, id_categoria, tipo_precio) -> int:
    with get_session() as session:
        producto = get_or_create(
            session,
            Producto,
            nombre=nombre,
            id_categoria=id_categoria,
            tipo_precio=tipo_precio,
        )
        return producto.id_producto


def insert_ticket(id_supermercado, fecha, id_mensaje_gmail, total, tienda, hora):
    with get_session() as session:
        ticket = get_or_create(
            session,
            Ticket,
            id_supermercado=id_supermercado,
            fecha=fecha,
            id_mensaje_gmail=id_mensaje_gmail,
            total=total,
            tienda=tienda,
            hora=hora,
        )
        return ticket.id_ticket


def insert_linea_ticket(
    id_ticket,
    id_producto,
    cantidad,
    unidad_medida,
    precio_unitario,
    precio_total,
    oferta,
    descuento,
):
    with get_session() as session:
        linea = LineaTicket(
            id_ticket=id_ticket,
            id_producto=id_producto,
            cantidad=cantidad,
            unidad_medida=unidad_medida,
            precio_unitario=precio_unitario,
            precio_total=precio_total,
            oferta=oferta,
            descuento=descuento,
        )
        session.add(linea)
        session.commit()
