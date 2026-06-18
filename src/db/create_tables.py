"""
Utility script to create all database tables using SQLAlchemy ORM.

Run:
    python -m db.create_tables
"""

from __future__ import annotations

from src.db.connection import Base, engine
from src.config.logger import get_logger
from src.db.init_db import ensure_database_exists

logger = get_logger(__name__)


def create_all_tables():
    logger.info("Checking database existence...")
    ensure_database_exists()

    logger.info("Creating tables...")
    Base.metadata.create_all(engine)
    logger.info("All tables created successfully.")


if __name__ == "__main__":
    create_all_tables()