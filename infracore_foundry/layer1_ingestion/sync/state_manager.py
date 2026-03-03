"""Sync state persistence and retrieval."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from layer1_ingestion.registry.models import SyncState

logger = logging.getLogger(__name__)


class SyncStateManager:
    """Manages sync state for incremental extraction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_state(self, source_id: UUID) -> Optional[SyncState]:
        return self.db.query(SyncState).filter(SyncState.source_id == source_id).first()

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
        logger.info("Updated sync state", extra={"source_id": str(source_id), "fields": list(kwargs.keys())})
        return state

    def mark_running(self, source_id: UUID) -> SyncState:
        return self.update_state(
            source_id,
            status="running",
            last_sync_at=datetime.now(timezone.utc),
            error_message=None,
        )

    def mark_completed(self, source_id: UUID, records: int, duration: float, checksum: str) -> SyncState:
        return self.update_state(
            source_id,
            status="completed",
            last_successful_sync_at=datetime.now(timezone.utc),
            total_records_last_run=records,
            failed_records_last_run=0,
            sync_duration_seconds=duration,
            checksum_last_batch=checksum,
            error_message=None,
        )

    def mark_failed(self, source_id: UUID, error: str, records: int = 0, failed: int = 0) -> SyncState:
        return self.update_state(
            source_id,
            status="failed",
            total_records_last_run=records,
            failed_records_last_run=failed,
            error_message=error,
        )

    def reset_state(self, source_id: UUID) -> SyncState:
        return self.update_state(
            source_id,
            status="idle",
            last_extracted_id=None,
            last_extracted_timestamp=None,
            error_message=None,
            checksum_last_batch=None,
        )
