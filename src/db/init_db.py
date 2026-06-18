"""
Database initialization utilities:
- Ensure the database exists
- Create tables if needed
Supports both PostgreSQL and SQLite.
"""

from __future__ import annotations

from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)


def ensure_database_exists():
    """
    Ensure that the target database exists.
    
    For PostgreSQL: Creates the database if it doesn't exist.
    For SQLite: No action needed (SQLite creates the file automatically).
    """
    db_url = settings.database_url

    if db_url.startswith("sqlite"):
        logger.info("Using SQLite - database will be created automatically.")
        return

    # PostgreSQL setup
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    db_name = settings.db_name
    db_user = settings.db_user
    db_password = settings.db_password
    db_host = settings.db_host
    db_port = settings.db_port

    try:
        # Connect to default 'postgres' database
        conn = psycopg2.connect(
            dbname="postgres",
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Check if DB exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
        exists = cur.fetchone()

        if exists:
            logger.info(f"Database '{db_name}' already exists.")
        else:
            logger.info(f"Database '{db_name}' does not exist. Creating...")
            cur.execute(f'CREATE DATABASE "{db_name}";')
            logger.info(f"Database '{db_name}' created successfully.")

        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error ensuring PostgreSQL database exists: {e}")
        raise
