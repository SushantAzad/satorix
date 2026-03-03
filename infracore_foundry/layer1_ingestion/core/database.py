"""
SQLAlchemy engine setup for PostgreSQL with connection pooling.
Provides session factory, FastAPI dependency, and table initialization.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy models."""
    pass


_engine = None
_SessionFactory = None


def get_engine():
    """
    Get or create the SQLAlchemy engine with connection pooling.
    Uses pool_size=10, max_overflow=20 for production workloads.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.log_level == "DEBUG",
        )
        logger.info(
            "SQLAlchemy engine created",
            extra={
                "host": settings.postgres_host,
                "database": settings.postgres_db,
                "pool_size": 10,
                "max_overflow": 20,
            },
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _SessionFactory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.
    Automatically closes the session when the request is complete.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions outside of FastAPI request lifecycle.
    Use this in Airflow tasks, background jobs, and CLI scripts.

    Usage:
        with get_db_context() as db:
            sources = db.query(DataSource).all()
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Initialize the database by creating all tables defined in models.
    Should be called on application startup.
    """
    # Import all models so they register with Base.metadata
    import layer1_ingestion.registry.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified successfully")

    # Verify connectivity
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        result.fetchone()
        logger.info("Database connectivity verified")


def close_db() -> None:
    """
    Close the database engine and dispose of all connections.
    Should be called on application shutdown.
    """
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        logger.info("Database engine disposed")
        _engine = None
        _SessionFactory = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Database initialized successfully")
