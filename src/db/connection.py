"""
src/db/connection.py

Database engine and session factory.

Engine and SessionLocal are initialized lazily on first use, not at import
time.  This means:
  - Importing any module that imports from src.db.connection does NOT
    attempt a database connection.  Tests and CLI scripts that don't need
    the database can import freely without monkeypatching.
  - Tests patch connection.SessionLocal with their own test session factory
    before any database call is made.

Usage (same call-site syntax as before):
    from src.db import connection
    db = connection.SessionLocal()   # creates a session
    try:
        ...
        db.commit()
    finally:
        db.close()
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.pool import QueuePool, StaticPool

from src.config.settings import settings


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models.
    Defined at module level because it is a class, not a connection —
    safe to instantiate at import time.
    """


# ── Private singletons ──────────────────────────────────────────────────────

_engine = None
_session_factory = None


# ── Internal factory ────────────────────────────────────────────────────────

def _build_engine():
    """Create the SQLAlchemy engine from settings."""
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
            future=True,
        )
    return create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
        future=True,
    )


# ── Public API ───────────────────────────────────────────────────────────────

def get_engine():
    """Return the singleton engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def SessionLocal() -> Session:
    """
    Create and return a new database session.

    The underlying engine and session factory are initialized on first call.
    Calling convention is identical to a sessionmaker instance:

        db = connection.SessionLocal()

    Tests replace this attribute via monkeypatch:

        monkeypatch.setattr(conn_module, "SessionLocal", TestSession)

    where TestSession is any callable that returns a Session-compatible object.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory()


def get_session() -> Session:
    """Alias for SessionLocal() — prefer in new code for clarity."""
    return SessionLocal()