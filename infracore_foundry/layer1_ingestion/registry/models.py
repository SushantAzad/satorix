"""
SQLAlchemy models for the data source registry.
Defines DataSource, SyncState, SyncRun, DataSourceHealth, and Alert tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Index, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from layer1_ingestion.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id = Column(String(255), nullable=False, index=True)
    source_name = Column(String(500), nullable=False)
    source_type = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    connection_config = Column(Text, nullable=False)          # AES-256-GCM encrypted JSON blob
    auth_method = Column(String(100), nullable=True)
    environment = Column(String(50), nullable=False, default="production")
    status = Column(String(50), nullable=False, default="active", index=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    circuit_open = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by = Column(String(255), nullable=True)

    sync_states = relationship("SyncState", back_populates="data_source", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="data_source", cascade="all, delete-orphan")
    health_checks = relationship("DataSourceHealth", back_populates="data_source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_data_sources_client_status", "client_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, name={self.source_name}, type={self.source_type})>"


class SyncState(Base):
    __tablename__ = "sync_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_extracted_id = Column(String(500), nullable=True)
    last_extracted_timestamp = Column(DateTime(timezone=True), nullable=True)
    total_records_last_run = Column(Integer, nullable=True)
    failed_records_last_run = Column(Integer, nullable=True, default=0)
    sync_duration_seconds = Column(Float, nullable=True)
    status = Column(String(50), nullable=False, default="idle")
    error_message = Column(Text, nullable=True)
    checksum_last_batch = Column(String(128), nullable=True)
    schema_fingerprint = Column(String(64), nullable=True)
    incremental_strategy = Column(String(30), nullable=True, default="timestamp")

    data_source = relationship("DataSource", back_populates="sync_states")

    def __repr__(self) -> str:
        return f"<SyncState(source_id={self.source_id}, status={self.status})>"


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Deterministic idempotency key: SHA256(source_id:sync_type:date_partition)[:16]
    batch_id = Column(String(64), nullable=True, unique=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_extracted = Column(Integer, nullable=True, default=0)
    records_failed = Column(Integer, nullable=True, default=0)
    output_path = Column(String(1000), nullable=True)
    sync_type = Column(String(50), nullable=False, default="full")
    status = Column(String(50), nullable=False, default="running", index=True)
    error_details = Column(Text, nullable=True)

    data_source = relationship("DataSource", back_populates="sync_runs")

    __table_args__ = (
        Index("ix_sync_runs_source_started", "source_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<SyncRun(id={self.id}, source_id={self.source_id}, status={self.status})>"


class DataSourceHealth(Base):
    __tablename__ = "data_source_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checked_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    is_reachable = Column(Boolean, nullable=False, default=False)
    response_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    schema_matches = Column(Boolean, nullable=True)
    schema_fingerprint = Column(String(64), nullable=True)
    freshness_score = Column(Float, nullable=True)
    volume_anomaly = Column(Boolean, nullable=False, default=False)
    alert_sent = Column(Boolean, nullable=False, default=False)
    alert_type = Column(String(100), nullable=True)

    data_source = relationship("DataSource", back_populates="health_checks")

    __table_args__ = (
        Index("ix_health_source_checked", "source_id", "checked_at"),
    )

    def __repr__(self) -> str:
        return f"<DataSourceHealth(source_id={self.source_id}, reachable={self.is_reachable})>"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(String(255), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=True)
    # status lifecycle: open → acknowledged → resolved
    status = Column(String(50), nullable=False, default="open", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_note = Column(Text, nullable=True)

    __table_args__ = (
        # One open alert per source per alert_type — deduplication at DB level
        Index("ix_alerts_source_type_open", "source_id", "alert_type",
              postgresql_where=Column("status") == "open", unique=True),
        Index("ix_alerts_source_active", "source_id", "status"),
        Index("ix_alerts_severity_status", "severity", "status"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, type={self.alert_type}, severity={self.severity}, status={self.status})>"
