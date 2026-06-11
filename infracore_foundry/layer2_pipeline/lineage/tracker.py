"""
Field-level lineage tracker.
Flushes LineageEvent objects from the ExecutionContext into the l2_lineage table.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from layer2_pipeline.core.context import ExecutionContext, LineageEvent
from layer2_pipeline.models.db_models import LineageRecord

logger = logging.getLogger(__name__)


class LineageTracker:
    """
    Writes lineage events accumulated in an ExecutionContext to the database.
    Called once per pipeline run, after all steps complete successfully.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def flush(self, context: ExecutionContext) -> int:
        """
        Write all lineage events from context to l2_lineage.
        Returns the number of records written.
        """
        if not context.lineage_events:
            return 0

        records = [
            self._to_db_record(event, context)
            for event in context.lineage_events
        ]
        try:
            self.db.bulk_save_objects(records)
            self.db.commit()
            logger.info(
                "Lineage flush: wrote %d records for run %s",
                len(records), context.run_id,
            )
            return len(records)
        except Exception as exc:
            self.db.rollback()
            logger.error("Lineage flush failed for run %s: %s", context.run_id, exc)
            raise

    def _to_db_record(self, event: LineageEvent, context: ExecutionContext) -> LineageRecord:
        # context.run_id is uuid4().hex — 32-char hex without dashes. Parse to UUID.
        try:
            run_uuid = uuid.UUID(context.run_id)
        except (ValueError, AttributeError):
            run_uuid = None
        return LineageRecord(
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            field_name=event.field_name,
            source_batch_id=event.source_batch_id or context.input_batch_id,
            source_path=context.input_path,
            pipeline_run_id=run_uuid,
            pipeline_id=context.pipeline_id,
            pipeline_version=context.pipeline_version,
            step_id=event.step_id,
            transform_applied=event.transform_applied,
            loaded_at=datetime.now(timezone.utc),
        )

    def get_lineage_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        field_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[LineageRecord]:
        """Query lineage history for a specific entity (used by the API)."""
        q = (
            self.db.query(LineageRecord)
            .filter(
                LineageRecord.entity_type == entity_type,
                LineageRecord.entity_id == entity_id,
            )
        )
        if field_name:
            q = q.filter(LineageRecord.field_name == field_name)
        return q.order_by(LineageRecord.loaded_at.desc()).limit(limit).all()
