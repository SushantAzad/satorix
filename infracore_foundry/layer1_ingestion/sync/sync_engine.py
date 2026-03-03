"""Main sync orchestrator: coordinates connectors, incremental strategies, and state."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import pandas as pd
from sqlalchemy.orm import Session

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ExtractionConfig, IncrementalConfig,
)
from layer1_ingestion.core.storage import upload_parquet, generate_object_path
from layer1_ingestion.registry.models import DataSource, SyncRun
from layer1_ingestion.sync.state_manager import SyncStateManager

logger = logging.getLogger(__name__)


class SyncEngine:
    """Main sync orchestrator for data extraction pipelines."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.state_manager = SyncStateManager(db)

    def run_sync(
        self,
        source: DataSource,
        connector: BaseConnector,
        sync_type: str = "incremental",
        client_id: Optional[str] = None,
    ) -> SyncRun:
        """Run a full or incremental sync for a data source."""
        cid = client_id or source.client_id
        run = SyncRun(
            source_id=source.id,
            sync_type=sync_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        self.state_manager.mark_running(source.id)
        start = time.perf_counter()

        try:
            if sync_type == "full":
                config = ExtractionConfig(
                    source_id=str(source.id), client_id=cid,
                )
                df = connector.extract_full(config)
            else:
                state = self.state_manager.get_state(source.id)
                config = IncrementalConfig(
                    source_id=str(source.id), client_id=cid,
                    strategy=source.source_type if source.source_type in ("timestamp", "sequence", "cdc") else "timestamp",
                    last_extracted_at=state.last_extracted_timestamp if state else None,
                    last_extracted_id=state.last_extracted_id if state else None,
                )
                df = connector.extract_incremental(config)

            duration = time.perf_counter() - start

            if df.empty:
                run.records_extracted = 0
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                self.state_manager.mark_completed(source.id, 0, duration, "")
            else:
                object_path = generate_object_path(cid, str(source.id))
                output_path = upload_parquet(df, "raw-data", object_path)
                checksum = connector.compute_checksum(df)

                run.records_extracted = len(df)
                run.output_path = output_path
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                self.state_manager.mark_completed(source.id, len(df), duration, checksum)

            self.db.commit()
            logger.info(
                "Sync completed",
                extra={
                    "source_id": str(source.id),
                    "records": run.records_extracted,
                    "duration": round(duration, 2),
                    "sync_type": sync_type,
                },
            )
            return run

        except Exception as e:
            duration = time.perf_counter() - start
            run.status = "failed"
            run.error_details = str(e)
            run.completed_at = datetime.now(timezone.utc)
            self.state_manager.mark_failed(source.id, str(e))
            self.db.commit()
            logger.error(
                "Sync failed: %s", str(e),
                extra={"source_id": str(source.id), "sync_type": sync_type},
            )
            return run

    def get_sync_history(self, source_id: UUID, limit: int = 30) -> list[SyncRun]:
        return (
            self.db.query(SyncRun)
            .filter(SyncRun.source_id == source_id)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
            .all()
        )
