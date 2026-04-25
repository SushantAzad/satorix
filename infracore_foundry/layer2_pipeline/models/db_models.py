"""
SQLAlchemy models for Layer 2 pipeline state, lineage, and error management.
All tables prefixed with l2_ to coexist with Layer 1 in the same database.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean,
    DateTime, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from layer1_ingestion.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> uuid.UUID:
    return uuid.uuid4()


class PipelineDefinition(Base):
    """Versioned pipeline definitions stored in the DB (authoritative source is YAML in Git)."""

    __tablename__ = "l2_pipeline_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    pipeline_id = Column(String(200), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    client_id = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False)       # full parsed YAML as JSON
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    created_by = Column(String(255), nullable=True)

    runs = relationship("PipelineRun", back_populates="pipeline", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_l2_pipeline_client_id", "pipeline_id", "client_id"),
        Index("ix_l2_pipeline_active", "pipeline_id", "is_active"),
    )


class PipelineRun(Base):
    """One execution of a pipeline against one input batch."""

    __tablename__ = "l2_pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    pipeline_definition_id = Column(
        UUID(as_uuid=True), ForeignKey("l2_pipeline_definitions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Deterministic: SHA256(pipeline_id:version:input_batch_id)[:16]
    run_id = Column(String(64), nullable=True, unique=True, index=True)
    client_id = Column(String(255), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    triggered_by = Column(String(50), nullable=False, default="scheduler")  # scheduler|manual|layer1_event
    input_batch_id = Column(String(64), nullable=True)
    input_path = Column(String(1000), nullable=True)
    output_path = Column(String(1000), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_input = Column(Integer, nullable=True, default=0)
    records_output = Column(Integer, nullable=True, default=0)
    records_failed = Column(Integer, nullable=True, default=0)
    duration_seconds = Column(Float, nullable=True)
    error_summary = Column(Text, nullable=True)

    pipeline = relationship("PipelineDefinition", back_populates="runs")
    step_runs = relationship("PipelineStepRun", back_populates="run", cascade="all, delete-orphan")
    error_records = relationship("ErrorRecord", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_l2_runs_client_status", "client_id", "status"),
        Index("ix_l2_runs_started", "started_at"),
    )


class PipelineStepRun(Base):
    """Execution record for one step within a pipeline run."""

    __tablename__ = "l2_pipeline_step_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("l2_pipeline_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_id = Column(String(200), nullable=False)
    transform_type = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_in = Column(Integer, nullable=True, default=0)
    records_out = Column(Integer, nullable=True, default=0)
    records_failed = Column(Integer, nullable=True, default=0)
    error_message = Column(Text, nullable=True)
    config_snapshot = Column(JSONB, nullable=True)

    run = relationship("PipelineRun", back_populates="step_runs")

    __table_args__ = (
        Index("ix_l2_step_runs_run_step", "run_id", "step_id"),
    )


class ErrorRecord(Base):
    """Individual records that failed during pipeline processing — the dead letter queue."""

    __tablename__ = "l2_error_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("l2_pipeline_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_id = Column(String(200), nullable=False)
    error_type = Column(String(50), nullable=False, index=True)   # source|transform|system
    error_subtype = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False, default="error")
    original_record = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    # quarantined → reprocessed | discarded
    status = Column(String(30), nullable=False, default="quarantined", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)

    run = relationship("PipelineRun", back_populates="error_records")

    __table_args__ = (
        Index("ix_l2_errors_run_type", "run_id", "error_type"),
        Index("ix_l2_errors_status", "status"),
    )


class LineageRecord(Base):
    """Field-level provenance: which source → which transform → which ontology field."""

    __tablename__ = "l2_lineage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    entity_type = Column(String(100), nullable=False, index=True)   # company|director|project
    entity_id = Column(String(255), nullable=False, index=True)     # CIN, DIN, etc.
    field_name = Column(String(200), nullable=False)
    source_batch_id = Column(String(64), nullable=True)
    source_path = Column(String(1000), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    pipeline_id = Column(String(200), nullable=True)
    pipeline_version = Column(String(50), nullable=True)
    step_id = Column(String(200), nullable=True)
    transform_applied = Column(String(100), nullable=True)
    loaded_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_l2_lineage_entity", "entity_type", "entity_id"),
        Index("ix_l2_lineage_source", "source_batch_id"),
    )


class DatasetVersion(Base):
    """Immutable record of every successful pipeline output — the version registry."""

    __tablename__ = "l2_dataset_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    pipeline_run_id = Column(
        UUID(as_uuid=True), ForeignKey("l2_pipeline_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    pipeline_id = Column(String(200), nullable=False, index=True)
    pipeline_version = Column(String(50), nullable=False)
    client_id = Column(String(255), nullable=False, index=True)
    run_id_str = Column(String(64), nullable=False, index=True)
    input_batch_id = Column(String(64), nullable=True)
    input_path = Column(String(1000), nullable=True)
    output_path = Column(String(1000), nullable=True)
    schema_fingerprint = Column(String(64), nullable=True)
    records_output = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_l2_dv_pipeline_run", "pipeline_id", "run_id_str"),
        Index("ix_l2_dv_client_created", "client_id", "created_at"),
    )


class DedupGroup(Base):
    """Records of entity resolution decisions — which records were merged and why."""

    __tablename__ = "l2_dedup_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uid)
    run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    pipeline_id = Column(String(200), nullable=False)
    canonical_id = Column(String(255), nullable=False)     # the surviving record's key
    duplicate_ids = Column(JSONB, nullable=False)          # list of merged record keys
    merge_strategy = Column(String(50), nullable=False)    # latest|most_complete|highest_priority|manual
    confidence_score = Column(Float, nullable=True)
    requires_review = Column(Boolean, nullable=False, default=False)
    reviewed = Column(Boolean, nullable=False, default=False)
    reviewer_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_l2_dedup_run", "run_id"),
        Index("ix_l2_dedup_review", "requires_review", "reviewed"),
    )
