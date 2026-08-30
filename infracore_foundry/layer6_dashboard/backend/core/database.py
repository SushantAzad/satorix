"""
Layer 6 database — async SQLAlchemy engine, session factory, and table helpers.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import text

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Engine & session
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.postgres_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Table / ORM models
# ---------------------------------------------------------------------------

class L6User(Base):
    __tablename__ = "l6_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False, default="analyst")
    client_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_login = Column(DateTime(timezone=True), nullable=True)


class L6Watchlist(Base):
    __tablename__ = "l6_watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_watchlist_entry"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("l6_users.id"), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(255), nullable=False)
    entity_name = Column(String(500), nullable=True)
    added_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    notes = Column(Text, nullable=True)


class L6ReportCache(Base):
    __tablename__ = "l6_report_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("l6_users.id"), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(255), nullable=False)
    report_type = Column(String(100), nullable=False)
    report_content = Column(JSONB, nullable=True)
    generated_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)


class L6ImportJob(Base):
    __tablename__ = "l6_import_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("l6_users.id"), nullable=False)
    client_id = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    result = Column(JSONB, nullable=False)
    status = Column(String(30), nullable=False, default="ready")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class L6SignalState(Base):
    __tablename__ = "l6_signal_state"
    client_id = Column(String(100), primary_key=True)
    payload = Column(JSONB, nullable=False, default=dict)
    scanned_at = Column(DateTime(timezone=True), nullable=True)


class L6RecentView(Base):
    __tablename__ = "l6_recent_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("l6_users.id"), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(255), nullable=False)
    entity_name = Column(String(500), nullable=True)
    risk_score = Column(Integer, nullable=True)
    viewed_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use in a request."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables (idempotent — uses CREATE TABLE IF NOT EXISTS via SQLAlchemy)."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Layer 6 database tables initialised.")
    except Exception as exc:
        logger.error("Failed to initialise Layer 6 database: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

async def upsert_recent_view(
    db: AsyncSession,
    user_id: str,
    entity_type: str,
    entity_id: str,
    entity_name: str,
    risk_score: int,
) -> None:
    """
    Insert or update a recent-view record for *user_id*, then prune so that at
    most the 20 most-recent views per user are kept.
    """
    try:
        # Delete existing view for the same entity (to update timestamp)
        await db.execute(
            text(
                """
                DELETE FROM l6_recent_views
                WHERE user_id = :user_id
                  AND entity_type = :entity_type
                  AND entity_id = :entity_id
                """
            ),
            {
                "user_id": user_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

        # Insert fresh record
        await db.execute(
            text(
                """
                INSERT INTO l6_recent_views
                    (id, user_id, entity_type, entity_id, entity_name, risk_score, viewed_at)
                VALUES
                    (:id, :user_id, :entity_type, :entity_id, :entity_name, :risk_score, NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "risk_score": risk_score,
            },
        )

        # Prune: keep only the 20 most-recent rows per user
        await db.execute(
            text(
                """
                DELETE FROM l6_recent_views
                WHERE user_id = :user_id
                  AND id NOT IN (
                      SELECT id FROM l6_recent_views
                      WHERE user_id = :user_id
                      ORDER BY viewed_at DESC
                      LIMIT 20
                  )
                """
            ),
            {"user_id": user_id},
        )

        await db.commit()
    except Exception as exc:
        logger.warning("upsert_recent_view failed: %s", exc)
        await db.rollback()
