"""Main sync orchestrator: coordinates connectors, incremental strategies, and state."""

import hashlib
import logging
import struct
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ExtractionConfig, IncrementalConfig,
)
from layer1_ingestion.core.storage import (
    upload_parquet, generate_object_path, generate_batch_id, object_exists,
)
from layer1_ingestion.profiling.profiler import DataProfiler
from layer1_ingestion.registry.models import DataSource, SyncRun
from layer1_ingestion.sync.state_manager import SyncStateManager

logger = logging.getLogger(__name__)

_profiler = DataProfiler()


def _advisory_lock_key(source_id: str) -> int:
    """Convert source UUID string to a signed 64-bit integer for pg_advisory_xact_lock."""
    digest = hashlib.sha256(source_id.encode()).digest()[:8]
    return struct.unpack(">q", digest)[0]


def _extract_watermarks(
    df: pd.DataFrame,
    timestamp_col: Optional[str],
    id_col: Optional[str],
) -> tuple[Optional[datetime], Optional[str]]:
    """Extract max timestamp and max id from the extracted DataFrame."""
    new_ts: Optional[datetime] = None
    new_id: Optional[str] = None

    if timestamp_col and timestamp_col in df.columns:
        series = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        max_val = series.dropna().max()
        if not pd.isna(max_val):
            new_ts = max_val.to_pydatetime()

    if id_col and id_col in df.columns:
        max_val = df[id_col].dropna().max()
        if not pd.isna(max_val):
            new_id = str(max_val)

    return new_ts, new_id


def _schema_fingerprint(df: pd.DataFrame) -> str:
    """SHA-256 of sorted (column_name, dtype) pairs — detects schema changes."""
    schema_str = ",".join(
        f"{col}:{dtype}" for col, dtype in sorted(zip(df.columns, df.dtypes.astype(str)))
    )
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


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
        """
        Run a full or incremental sync for a data source.

        Guarantees:
        - Advisory lock prevents concurrent syncs for the same source.
        - Deterministic batch_id prevents duplicate Parquet files on re-runs.
        - Watermarks are advanced only after successful MinIO upload.
        - Profiling runs on every extracted batch.
        - Stale runs are cleaned up before each new run starts.
        """
        cid = client_id or source.client_id
        source_id_str = str(source.id)

        # --- Stale run cleanup ---
        cleaned = self.state_manager.cleanup_stale_runs(source.id)
        if cleaned:
            logger.info("Cleaned %d stale run(s) for source %s", cleaned, source_id_str)

        # --- Idempotency: deterministic batch_id ---
        now = datetime.now(timezone.utc)
        partition_key = now.strftime("%Y-%m-%dT%H")  # hourly granularity
        batch_id = generate_batch_id(source_id_str, sync_type, partition_key)

        existing_run = (
            self.db.query(SyncRun)
            .filter(SyncRun.batch_id == batch_id, SyncRun.status == "completed")
            .first()
        )
        if existing_run:
            logger.info(
                "Skipping sync — batch_id already completed",
                extra={"source_id": source_id_str, "batch_id": batch_id},
            )
            return existing_run

        # --- PostgreSQL advisory lock — prevents concurrent syncs per source ---
        lock_key = _advisory_lock_key(source_id_str)
        try:
            self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        except Exception as exc:
            raise RuntimeError(
                f"Could not acquire advisory lock for source {source_id_str}"
            ) from exc

        # --- Create SyncRun record ---
        run = SyncRun(
            source_id=source.id,
            batch_id=batch_id,
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
            state = self.state_manager.get_state(source.id)

            # --- Determine incremental strategy ---
            # Use the stored strategy; fall back to the source_type field only if it matches
            # a valid strategy name (legacy behaviour for bootstrap).
            strategy = (state.incremental_strategy if state and state.incremental_strategy
                        else "timestamp")

            if sync_type == "full":
                config = ExtractionConfig(
                    source_id=source_id_str,
                    client_id=cid,
                )
                df = connector.extract_full(config)
            else:
                config = IncrementalConfig(
                    source_id=source_id_str,
                    client_id=cid,
                    strategy=strategy,
                    last_extracted_at=(
                        state.last_extracted_timestamp if state else None
                    ),
                    last_extracted_id=(
                        state.last_extracted_id if state else None
                    ),
                )
                df = connector.extract_incremental(config)

            duration = time.perf_counter() - start

            if df.empty:
                run.records_extracted = 0
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                self.state_manager.mark_completed(source.id, 0, duration, "")
                logger.info(
                    "Sync completed (0 new records)",
                    extra={"source_id": source_id_str, "sync_type": sync_type},
                )
                return run

            # --- Schema fingerprint ---
            fingerprint = _schema_fingerprint(df)
            previous_fingerprint = self.state_manager.get_schema_fingerprint(source.id)
            if previous_fingerprint and previous_fingerprint != fingerprint:
                logger.warning(
                    "Schema changed for source %s: %s → %s",
                    source_id_str, previous_fingerprint, fingerprint,
                )

            # --- Upload to MinIO ---
            object_path = generate_object_path(cid, source_id_str, batch_id)

            if object_exists("raw-data", object_path):
                logger.info(
                    "Parquet already exists at %s, skipping upload", object_path,
                )
            else:
                upload_parquet(
                    df,
                    "raw-data",
                    object_path,
                    extra_metadata={
                        "satorix_batch_id": batch_id,
                        "satorix_source_id": source_id_str,
                        "satorix_client_id": cid,
                        "satorix_sync_type": sync_type,
                        "satorix_schema_fingerprint": fingerprint,
                    },
                )

            checksum = connector.compute_checksum(df)

            # --- Extract watermarks AFTER successful upload ---
            ts_col = (config.last_extracted_at is not None) and getattr(config, "strategy", "") == "timestamp"
            new_ts, new_id = _extract_watermarks(
                df,
                timestamp_col=self._find_timestamp_column(df, strategy),
                id_col=self._find_id_column(df, strategy),
            )

            # --- Run profiler ---
            try:
                profile = _profiler.profile(df, source_id=source_id_str)
                logger.info(
                    "Profiling complete: quality_score=%.1f, issues=%d",
                    profile.overall_quality_score,
                    len(profile.cross_field_issues),
                    extra={"source_id": source_id_str},
                )
            except Exception as profile_exc:
                logger.warning(
                    "Profiling failed (non-fatal): %s",
                    str(profile_exc),
                    extra={"source_id": source_id_str},
                )

            # --- Finalize run ---
            run.records_extracted = len(df)
            run.output_path = object_path
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            # Notify Layer 2 — Kafka primary, Redis fallback (both non-fatal)
            _event_payload = {
                "batch_id": batch_id,
                "source_id": source_id_str,
                "client_id": cid,
                "output_path": object_path,
                "records": len(df),
                "schema_fingerprint": fingerprint,
            }

            # Primary: Kafka (topic: layer1.raw.parquet.ready)
            _kafka_ok = False
            try:
                from layer1_ingestion.streaming.kafka_producer import get_publisher
                _kafka_ok = get_publisher().publish(
                    topic="layer1.raw.parquet.ready",
                    event=_event_payload,
                    key=source_id_str,
                )
            except Exception as _kafka_exc:
                logger.warning("Kafka notify failed (falling back to Redis): %s", _kafka_exc)

            # Fallback: Redis LPUSH (kept for backward compatibility with Airflow DAG polling)
            try:
                import json as _json, os as _os
                import redis as _redis
                _r = _redis.from_url(_os.environ.get("REDIS_URL", "redis://redis:6379/0"))
                _r.lpush("layer1:sync:complete", _json.dumps(_event_payload))
                if not _kafka_ok:
                    logger.info("Layer 2 notified via Redis (Kafka unavailable): batch_id=%s", batch_id)
            except Exception as _redis_exc:
                logger.warning("Redis notify failed (non-fatal): %s", _redis_exc)

            self.state_manager.mark_completed(
                source.id,
                records=len(df),
                duration=duration,
                checksum=checksum,
                last_extracted_timestamp=new_ts,
                last_extracted_id=new_id,
                schema_fingerprint=fingerprint,
            )

            logger.info(
                "Sync completed",
                extra={
                    "source_id": source_id_str,
                    "records": len(df),
                    "duration": round(duration, 2),
                    "sync_type": sync_type,
                    "batch_id": batch_id,
                    "new_watermark_ts": new_ts.isoformat() if new_ts else None,
                    "new_watermark_id": new_id,
                },
            )
            return run

        except Exception as exc:
            duration = time.perf_counter() - start
            run.status = "failed"
            run.error_details = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.state_manager.mark_failed(source.id, str(exc))
            logger.error(
                "Sync failed: %s",
                str(exc),
                extra={"source_id": source_id_str, "sync_type": sync_type},
                exc_info=True,
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

    @staticmethod
    def _find_timestamp_column(df: pd.DataFrame, strategy: str) -> Optional[str]:
        """Best-effort: find the most likely watermark timestamp column."""
        if strategy != "timestamp":
            return None
        preferred = ["updated_at", "modified_at", "last_modified", "created_at", "timestamp"]
        for name in preferred:
            if name in df.columns:
                return name
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return str(col)
        return None

    @staticmethod
    def _find_id_column(df: pd.DataFrame, strategy: str) -> Optional[str]:
        """Best-effort: find the most likely watermark sequence/ID column."""
        if strategy != "sequence":
            return None
        preferred = ["id", "record_id", "seq", "sequence_number", "row_id"]
        for name in preferred:
            if name in df.columns:
                return name
        return None
