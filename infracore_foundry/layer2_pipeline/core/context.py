"""
Execution context — the single object threaded through every step of a pipeline run.
Holds mutable state (metrics, warnings, lineage events) so transforms never need
to touch the database directly.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class StepMetrics:
    step_id: str
    transform_type: str
    records_in: int = 0
    records_out: int = 0
    records_failed: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class LineageEvent:
    entity_type: str
    entity_id: str
    field_name: str
    step_id: str
    transform_applied: str
    source_batch_id: Optional[str] = None


@dataclass
class FailedRecord:
    step_id: str
    error_type: str        # source | transform | system
    error_subtype: str
    error_message: str
    severity: str = "error"
    original_record: Optional[dict] = None


@dataclass
class ExecutionContext:
    """
    Threaded through every transform step during a pipeline run.
    Immutable run metadata; mutable accumulators for metrics/lineage/errors.
    """
    run_id: str
    pipeline_id: str
    pipeline_version: str
    client_id: str
    input_batch_id: Optional[str]
    input_path: Optional[str]
    triggered_by: str = "scheduler"

    # Mutable accumulators — updated by transforms and the executor
    step_metrics: dict[str, StepMetrics] = field(default_factory=dict)
    lineage_events: list[LineageEvent] = field(default_factory=list)
    failed_records: list[FailedRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _step_start_times: dict[str, float] = field(default_factory=dict, repr=False)

    def begin_step(self, step_id: str, transform_type: str) -> None:
        self._step_start_times[step_id] = time.monotonic()
        self.step_metrics[step_id] = StepMetrics(
            step_id=step_id,
            transform_type=transform_type,
            started_at=datetime.now(timezone.utc),
        )

    def end_step(
        self,
        step_id: str,
        records_in: int,
        records_out: int,
        records_failed: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        m = self.step_metrics.get(step_id)
        if m is None:
            return
        m.completed_at = datetime.now(timezone.utc)
        m.records_in = records_in
        m.records_out = records_out
        m.records_failed = records_failed
        m.error_message = error_message

    def add_lineage(
        self,
        entity_type: str,
        entity_id: str,
        field_name: str,
        step_id: str,
        transform_applied: str,
    ) -> None:
        self.lineage_events.append(
            LineageEvent(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                step_id=step_id,
                transform_applied=transform_applied,
                source_batch_id=self.input_batch_id,
            )
        )

    def add_failed_record(
        self,
        step_id: str,
        error_type: str,
        error_subtype: str,
        error_message: str,
        severity: str = "error",
        original_record: Optional[dict] = None,
    ) -> None:
        self.failed_records.append(
            FailedRecord(
                step_id=step_id,
                error_type=error_type,
                error_subtype=error_subtype,
                error_message=error_message,
                severity=severity,
                original_record=original_record,
            )
        )

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def total_records_failed(self) -> int:
        return sum(m.records_failed for m in self.step_metrics.values())

    @classmethod
    def create(
        cls,
        pipeline_id: str,
        pipeline_version: str,
        client_id: str,
        input_batch_id: Optional[str] = None,
        input_path: Optional[str] = None,
        triggered_by: str = "scheduler",
    ) -> "ExecutionContext":
        return cls(
            run_id=uuid.uuid4().hex,
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            client_id=client_id,
            input_batch_id=input_batch_id,
            input_path=input_path,
            triggered_by=triggered_by,
        )
