"""
SQLAlchemy models for the data source registry.
Defines DataSource, SyncState, SyncRun, and DataSourceHealth tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from layer1_ingestion.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class DataSource(Base):
    """Registry of all connected data sources."""

    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id = Column(String(255), nullable=False, index=True)
    source_name = Column(String(500), nullable=False)
    source_type = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    connection_config = Column(Text, nullable=False)  # JSON, encrypted
    auth_method = Column(String(100), nullable=True)
    environment = Column(String(50), nullable=False, default="production")
    status = Column(String(50), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    sync_states = relationship("SyncState", back_populates="data_source", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="data_source", cascade="all, delete-orphan")
    health_checks = relationship("DataSourceHealth", back_populates="data_source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_data_sources_client_status", "client_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, name={self.source_name}, type={self.source_type})>"


class SyncState(Base):
    """Tracks incremental sync state for each data source."""

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

    # Relationships
    data_source = relationship("DataSource", back_populates="sync_states")

    def __repr__(self) -> str:
        return f"<SyncState(source_id={self.source_id}, status={self.status})>"


class SyncRun(Base):
    """Individual sync run records for audit and troubleshooting."""

    __tablename__ = "sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_extracted = Column(Integer, nullable=True, default=0)
    records_failed = Column(Integer, nullable=True, default=0)
    output_path = Column(String(1000), nullable=True)
    sync_type = Column(String(50), nullable=False, default="full")
    status = Column(String(50), nullable=False, default="running", index=True)
    error_details = Column(Text, nullable=True)

    # Relationships
    data_source = relationship("DataSource", back_populates="sync_runs")

    __table_args__ = (
        Index("ix_sync_runs_source_started", "source_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<SyncRun(id={self.id}, source_id={self.source_id}, status={self.status})>"


class DataSourceHealth(Base):
    """Health check results for monitoring data source connectivity and quality."""

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
    schema_matches = Column(Boolean, nullable=True)
    freshness_score = Column(Float, nullable=True)  # 0.0 to 1.0
    volume_anomaly = Column(Boolean, nullable=False, default=False)
    alert_sent = Column(Boolean, nullable=False, default=False)
    alert_type = Column(String(100), nullable=True)

    # Relationships
    data_source = relationship("DataSource", back_populates="health_checks")

    __table_args__ = (
        Index("ix_health_source_checked", "source_id", "checked_at"),
    )

    def __repr__(self) -> str:
        return f"<DataSourceHealth(source_id={self.source_id}, reachable={self.is_reachable})>"


class Alert(Base):
    """Alert records for health monitoring notifications."""

    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    source_id = Column(String(255), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_note = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        Index("ix_alerts_source_active", "source_id", "is_active"),
        Index("ix_alerts_severity_active", "severity", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, type={self.alert_type}, severity={self.severity})>"
