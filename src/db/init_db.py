"""
Database initialization utilities:
- Ensure the database exists
- Create tables if needed
"""

from __future__ import annotations

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)


def ensure_database_exists():
    """
    Ensure that the target PostgreSQL database exists.
    If not, create it.
    """
    db_name = settings.db_name
    db_user = settings.db_user
    db_password = settings.db_password
    db_host = settings.db_host
    db_port = settings.db_port

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
