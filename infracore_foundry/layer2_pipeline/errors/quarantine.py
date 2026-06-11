"""
Dead letter queue (DLQ) management.
Persists failed records from ExecutionContext to l2_error_records.
Provides retry and resolution workflows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from layer2_pipeline.core.context import ExecutionContext, FailedRecord
from layer2_pipeline.errors.classifier import ClassifiedError
from layer2_pipeline.models.db_models import ErrorRecord

logger = logging.getLogger(__name__)


class QuarantineManager:
    """
    Flush failed records to the l2_error_records table.
    Supports bulk quarantine, retry counting, and resolution.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def flush(self, context: ExecutionContext, run_id: uuid.UUID) -> int:
        """
        Write all failed records from context to the dead letter table.
        Returns the count of records written.
        """
        if not context.failed_records:
            return 0

        records = [
            self._to_db_record(fr, run_id)
            for fr in context.failed_records
        ]
        try:
            self.db.bulk_save_objects(records)
            self.db.commit()
            logger.info("Quarantined %d failed records for run %s", len(records), run_id)
            return len(records)
        except Exception as exc:
            self.db.rollback()
            logger.error("Failed to write error records for run %s: %s", run_id, exc)
            raise

    def quarantine_classified(
        self, run_id: uuid.UUID, classified: ClassifiedError
    ) -> ErrorRecord:
        """Directly quarantine a ClassifiedError (for pipeline-level failures)."""
        record = ErrorRecord(
            run_id=run_id,
            step_id=classified.step_id or "pipeline",
            error_type=classified.error_type.value,
            error_subtype=classified.error_subtype.value,
            severity=classified.severity,
            error_message=classified.message,
            status="quarantined",
        )
        try:
            self.db.add(record)
            self.db.commit()
            return record
        except Exception:
            self.db.rollback()
            raise

    def get_quarantined(
        self, run_id: Optional[uuid.UUID] = None, limit: int = 100
    ) -> list[ErrorRecord]:
        q = self.db.query(ErrorRecord).filter(ErrorRecord.status == "quarantined")
        if run_id is not None:
            q = q.filter(ErrorRecord.run_id == run_id)
        return q.order_by(ErrorRecord.created_at.desc()).limit(limit).all()

    def mark_reprocessed(self, error_id: uuid.UUID, note: str = "") -> Optional[ErrorRecord]:
        record = self.db.query(ErrorRecord).get(error_id)
        if record is None:
            return None
        record.status = "reprocessed"
        record.resolved_at = datetime.now(timezone.utc)
        record.resolution_note = note
        self.db.commit()
        return record

    def mark_discarded(self, error_id: uuid.UUID, note: str = "") -> Optional[ErrorRecord]:
        record = self.db.query(ErrorRecord).get(error_id)
        if record is None:
            return None
        record.status = "discarded"
        record.resolved_at = datetime.now(timezone.utc)
        record.resolution_note = note
        self.db.commit()
        return record

    def increment_retry(self, error_id: uuid.UUID) -> Optional[ErrorRecord]:
        record = self.db.query(ErrorRecord).get(error_id)
        if record is None:
            return None
        record.retry_count += 1
        self.db.commit()
        return record

    def _to_db_record(self, fr: FailedRecord, run_id: uuid.UUID) -> ErrorRecord:
        return ErrorRecord(
            run_id=run_id,
            step_id=fr.step_id,
            error_type=fr.error_type,
            error_subtype=fr.error_subtype,
            severity=fr.severity,
            original_record=fr.original_record,
            error_message=fr.error_message,
            status="quarantined",
            created_at=datetime.now(timezone.utc),
        )
