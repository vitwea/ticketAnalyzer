"""
alembic/env.py

Migration environment for ticketAnalyzer.

Key decisions:
  - DB URL comes from src.config.settings, not from alembic.ini, so that
    the same .env file drives both the application and migrations.
  - render_as_batch is True: this makes ALTER TABLE operations work on
    SQLite (used in tests) by recreating the table, while still generating
    efficient ALTER statements on PostgreSQL.
  - target_metadata is Base.metadata with all models imported, so
    `alembic revision --autogenerate` can diff against the ORM definitions.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make src/ importable ──────────────────────────────────────────────────────
# Alembic runs from the project root, but src/ is not always on sys.path.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.settings import settings          # noqa: E402
from src.db.connection import Base                # noqa: E402
from src.db import models  # noqa: F401, E402   — registers all ORM models

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

# Override the URL from settings so we never need to hard-code it in alembic.ini
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


# ── Migration modes ───────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Generate SQL script without a live DB connection (--sql flag).
    Useful for producing migration scripts to run manually on production.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # render_as_batch=True lets ALTER TABLE work on SQLite
            # (recreates the table) and runs as standard ALTER on PostgreSQL.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()