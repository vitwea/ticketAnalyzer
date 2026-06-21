from sqlalchemy.exc import IntegrityError
from src.db import connection
from src.db.models import Supermercado, Categoria, Producto, Ticket, LineaTicket, Tienda
from src.config.logger import get_logger

logger = get_logger(__name__)


def insert_supermercado(nombre: str) -> int:
    """
    Insert or retrieve a supermarket by name.
    Uses upsert logic to avoid duplicates.
    """
    db = connection.SessionLocal()
    try:
        sup = db.query(Supermercado).filter_by(nombre=nombre).first()
        if sup:
            return sup.id

        sup = Supermercado(nombre=nombre)
        db.add(sup)
        db.commit()
        logger.debug(f"Inserted new supermercado: {nombre} (id={sup.id})")
        return sup.id
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting supermercado {nombre}: {e}")
        # Try again after rollback
        sup = db.query(Supermercado).filter_by(nombre=nombre).first()
        if sup:
            return sup.id
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting supermercado {nombre}: {e}")
        raise
    finally:
        db.close()


def insert_tienda(supermercado_id: int, direccion: str, codigo_postal: str, ciudad: str) -> int:
    """
    Insert or retrieve a store location.
    Uses upsert logic to avoid duplicates (unique by supermercado + direccion + codigo_postal).
    """
    db = connection.SessionLocal()
    try:
        tienda = (
            db.query(Tienda)
            .filter_by(supermercado_id=supermercado_id, direccion=direccion, codigo_postal=codigo_postal)
            .first()
        )
        if tienda:
            return tienda.id

        tienda = Tienda(
            supermercado_id=supermercado_id,
            direccion=direccion,
            codigo_postal=codigo_postal,
            ciudad=ciudad,
        )
        db.add(tienda)
        db.commit()
        logger.debug(f"Inserted new tienda: {direccion} (id={tienda.id})")
        return tienda.id
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting tienda {direccion}: {e}")
        raise
    finally:
        db.close()


def insert_categoria(nombre: str) -> int:
    """
    Insert or retrieve a product category by name.
    Uses upsert logic to avoid duplicates.
    """
    db = connection.SessionLocal()
    try:
        cat = db.query(Categoria).filter_by(nombre=nombre).first()
        if cat:
            return cat.id

        cat = Categoria(nombre=nombre)
        db.add(cat)
        db.commit()
        logger.debug(f"Inserted new categoria: {nombre} (id={cat.id})")
        return cat.id
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting categoria {nombre}: {e}")
        # Try again after rollback
        cat = db.query(Categoria).filter_by(nombre=nombre).first()
        if cat:
            return cat.id
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting categoria {nombre}: {e}")
        raise
    finally:
        db.close()


def insert_producto(nombre: str, id_categoria: int, unidad_medida: str) -> int:
    """
    Insert or retrieve a product.
    Uses upsert logic to avoid duplicates (unique by name + category + unit).
    """
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
        logger.debug(f"Inserted new producto: {nombre} (id={prod.id})")
        return prod.id
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting producto {nombre}: {e}")
        raise
    finally:
        db.close()


def insert_ticket(id_supermercado: int, fecha, id_mensaje_gmail: str,
                  total: float, tienda_id: int = None, hora = None) -> int:
    """
    Insert or retrieve a ticket by Gmail message ID.
    Uses upsert logic to prevent duplicate processing.
    """
    db = connection.SessionLocal()
    try:
        ticket = db.query(Ticket).filter_by(id_mensaje_gmail=id_mensaje_gmail).first()
        if ticket:
            logger.debug(f"Ticket already exists for Gmail message {id_mensaje_gmail}")
            return ticket.id

        ticket = Ticket(
            id_supermercado=id_supermercado,
            fecha=fecha,
            hora=hora,
            tienda_id=tienda_id,
            total=total,
            id_mensaje_gmail=id_mensaje_gmail,
        )
        db.add(ticket)
        db.commit()
        logger.debug(f"Inserted new ticket: {id_mensaje_gmail} (id={ticket.id})")
        return ticket.id
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Integrity error inserting ticket {id_mensaje_gmail}: {e}")
        # Try again after rollback
        ticket = db.query(Ticket).filter_by(id_mensaje_gmail=id_mensaje_gmail).first()
        if ticket:
            return ticket.id
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting ticket {id_mensaje_gmail}: {e}")
        raise
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
    """
    Insert a ticket line item.
    Each line is unique per ticket+producto combination.
    """
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
        logger.debug(f"Inserted linea_ticket {linea.id}")
        return linea.id
    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting linea_ticket: {e}")
        raise
    finally:
        db.close()