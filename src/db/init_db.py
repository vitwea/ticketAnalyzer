"""
src/db/init_db.py

Ensures the target database exists before SQLAlchemy tries to connect.

For PostgreSQL: creates the database if it doesn't exist, connecting first
  to the default 'postgres' admin database.
For SQLite: no-op — SQLite creates the file automatically on first write.

Uses SQLAlchemy instead of a raw psycopg2 connection (M-8): psycopg2 is
already an indirect dependency via the psycopg2-binary package, but using
the ORM layer keeps the codebase consistent and avoids a second low-level
connection pattern.
"""

from __future__ import annotations

from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)


def ensure_database_exists() -> None:
    """
    Ensure that the target database exists, creating it if necessary.

    For PostgreSQL this requires a connection to the 'postgres' system
    database (before the app database has been created), so we build a
    temporary engine with AUTOCOMMIT isolation — CREATE DATABASE cannot
    run inside a transaction.
    """
    db_url = settings.database_url

    if db_url.startswith("sqlite"):
        logger.info("Using SQLite — database file will be created automatically.")
        return

    # ── PostgreSQL ────────────────────────────────────────────────────────
    from sqlalchemy import create_engine, text

    db_name  = settings.db_name
    root_url = (
        f"postgresql+psycopg2://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/postgres"
    )

    try:
        # AUTOCOMMIT is required — DDL statements like CREATE DATABASE
        # cannot run inside a transaction block in PostgreSQL.
        engine = create_engine(root_url, isolation_level="AUTOCOMMIT", future=True)
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()

            if exists:
                logger.info("Database '%s' already exists.", db_name)
            else:
                logger.info("Database '%s' not found — creating...", db_name)
                # Identifier quoting: db_name comes from settings, not user input,
                # but we quote it defensively to handle names with special chars.
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                logger.info("Database '%s' created successfully.", db_name)
    except Exception as exc:
        logger.error("Error ensuring PostgreSQL database exists: %s", exc)
        raise
    finally:
        engine.dispose()