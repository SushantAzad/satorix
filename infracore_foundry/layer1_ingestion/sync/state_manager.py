"""Sync state persistence and retrieval."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from layer1_ingestion.registry.models import SyncState, SyncRun

logger = logging.getLogger(__name__)

# Runs stuck in 'running' longer than this are assumed dead (OOM kill, SIGKILL, etc.)
STALE_RUN_TIMEOUT_HOURS = 2


class SyncStateManager:
    """Manages sync state for incremental extraction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_state(self, source_id: UUID) -> Optional[SyncState]:
        return self.db.query(SyncState).filter(SyncState.source_id == source_id).first()

    def get_schema_fingerprint(self, source_id: UUID) -> Optional[str]:
        state = self.get_state(source_id)
        return state.schema_fingerprint if state else None

    def update_state(self, source_id: UUID, **kwargs) -> SyncState:
        state = self.get_state(source_id)
        if state is None:
            state = SyncState(source_id=source_id)
            self.db.add(state)

        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self.db.commit()
        self.db.refresh(state)
        logger.info(
            "Updated sync state",
            extra={"source_id": str(source_id), "fields": list(kwargs.keys())},
        )
        return state

    def mark_running(self, source_id: UUID) -> SyncState:
        return self.update_state(
            source_id,
            status="running",
            last_sync_at=datetime.now(timezone.utc),
            error_message=None,
        )

    def mark_completed(
        self,
        source_id: UUID,
        records: int,
        duration: float,
        checksum: str,
        last_extracted_timestamp: Optional[datetime] = None,
        last_extracted_id: Optional[str] = None,
        schema_fingerprint: Optional[str] = None,
    ) -> SyncState:
        fields: dict = {
            "status": "completed",
            "last_successful_sync_at": datetime.now(timezone.utc),
            "total_records_last_run": records,
            "failed_records_last_run": 0,
            "sync_duration_seconds": duration,
            "checksum_last_batch": checksum,
            "error_message": None,
        }
        # Only advance watermarks when we actually have new values.
        # Never reset a valid watermark to None.
        if last_extracted_timestamp is not None:
            fields["last_extracted_timestamp"] = last_extracted_timestamp
        if last_extracted_id is not None:
            fields["last_extracted_id"] = str(last_extracted_id)
        if schema_fingerprint is not None:
            fields["schema_fingerprint"] = schema_fingerprint
        return self.update_state(source_id, **fields)

    def mark_failed(
        self,
        source_id: UUID,
        error: str,
        records: int = 0,
        failed: int = 0,
    ) -> SyncState:
        return self.update_state(
            source_id,
            status="failed",
            total_records_last_run=records,
            failed_records_last_run=failed,
            error_message=error,
        )

    def reset_state(self, source_id: UUID) -> SyncState:
        """Full reset — only for explicit operator action, not automatic recovery."""
        return self.update_state(
            source_id,
            status="idle",
            last_extracted_id=None,
            last_extracted_timestamp=None,
            error_message=None,
            checksum_last_batch=None,
            schema_fingerprint=None,
        )

    def cleanup_stale_runs(self, source_id: Optional[UUID] = None) -> int:
        """
        Mark runs stuck in 'running' for > STALE_RUN_TIMEOUT_HOURS as 'failed'.
        Returns the number of runs cleaned up.

        Call this at the start of every sync to prevent ghost 'running' states
        caused by OOM kills or SIGKILL.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_RUN_TIMEOUT_HOURS)
        query = self.db.query(SyncRun).filter(
            SyncRun.status == "running",
            SyncRun.started_at < cutoff,
        )
        if source_id is not None:
            query = query.filter(SyncRun.source_id == source_id)

        stale_runs = query.all()
        count = len(stale_runs)
        for run in stale_runs:
            run.status = "failed"
            run.error_details = (
                f"Marked failed by cleanup: run exceeded {STALE_RUN_TIMEOUT_HOURS}h "
                "timeout. Process was likely killed externally (OOM, SIGKILL)."
            )
            run.completed_at = datetime.now(timezone.utc)
            # Also reset sync_state for this source so next run is not blocked
            self.update_state(
                run.source_id,
                status="idle",
                error_message="Previous run timed out and was cleaned up.",
            )
            logger.warning(
                "Cleaned up stale sync run",
                extra={
                    "run_id": str(run.id),
                    "source_id": str(run.source_id),
                    "started_at": run.started_at.isoformat(),
                },
            )

        if count > 0:
            self.db.commit()

        return count
