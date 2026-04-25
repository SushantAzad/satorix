"""
Stream processor: converts Kafka micro-batches into the same storage format
and DB records as batch ingestion.

Each micro-batch:
  1. Converts to DataFrame
  2. Computes a deterministic batch_id from topic + offset range
  3. Uploads to MinIO raw-data bucket (same Parquet format as batch)
  4. Creates a SyncRun record
  5. Publishes to Redis layer1:sync:complete → triggers Layer 2
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from layer1_ingestion.core.storage import (
    generate_object_path,
    object_exists,
    upload_parquet,
)

logger = logging.getLogger(__name__)


def _stream_batch_id(topic: str, offset_tag: str) -> str:
    """Deterministic batch_id for a streaming micro-batch."""
    content = f"stream:{topic}:{offset_tag}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class StreamProcessor:
    """
    Processes one Kafka micro-batch through the Layer 1 storage pipeline.

    Designed to be called from StreamingIngestionConsumer.on_batch.
    Maintains the same idempotency, storage, and event contracts as SyncEngine.
    """

    def __init__(
        self,
        client_id: str,
        source_id: str,
        db_session_factory,
        redis_url: str = "redis://redis:6379/0",
    ) -> None:
        self.client_id = client_id
        self.source_id = source_id
        self._db_factory = db_session_factory
        self._redis_url = redis_url

    def process(self, records: list[dict], topic: str, offset_tag: str) -> None:
        """
        Entry point called by the Kafka consumer on each micro-batch flush.
        Idempotent: if batch_id already completed, skips silently.
        """
        if not records:
            return

        batch_id = _stream_batch_id(topic, offset_tag)
        df = pd.DataFrame(records)

        # Remove internal Kafka metadata columns from the stored payload
        kafka_cols = [c for c in df.columns if c.startswith("_kafka_")]
        df = df.drop(columns=kafka_cols, errors="ignore")

        if df.empty:
            logger.info("Stream batch %s produced empty DataFrame — skipping", batch_id)
            return

        with self._db_factory() as db:
            from layer1_ingestion.registry.models import SyncRun

            # Idempotency check
            existing = db.query(SyncRun).filter(
                SyncRun.batch_id == batch_id,
                SyncRun.status == "completed",
            ).first()
            if existing:
                logger.info("Stream batch %s already completed — skipping", batch_id)
                return

            object_path = generate_object_path(self.client_id, self.source_id, batch_id)

            run = SyncRun(
                source_id=self.source_id,
                batch_id=batch_id,
                sync_type="streaming",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            try:
                if not object_exists("raw-data", object_path):
                    upload_parquet(
                        df,
                        "raw-data",
                        object_path,
                        extra_metadata={
                            "satorix_batch_id": batch_id,
                            "satorix_source_id": str(self.source_id),
                            "satorix_client_id": self.client_id,
                            "satorix_sync_type": "streaming",
                            "satorix_kafka_topic": topic,
                            "satorix_kafka_offsets": offset_tag,
                        },
                    )
                else:
                    logger.info("Stream Parquet already exists at %s — skipping upload", object_path)

                run.records_extracted = len(df)
                run.output_path = object_path
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()

                # Notify Layer 2
                self._notify_layer2(batch_id, object_path)

                logger.info(
                    "Stream batch processed: batch_id=%s topic=%s records=%d path=%s",
                    batch_id, topic, len(df), object_path,
                )

            except Exception as exc:
                run.status = "failed"
                run.error_details = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
                logger.error("Stream batch %s failed: %s", batch_id, exc)
                raise

    def _notify_layer2(self, batch_id: str, output_path: str) -> None:
        try:
            import redis as _redis
            r = _redis.from_url(self._redis_url)
            r.lpush(
                "layer1:sync:complete",
                json.dumps({
                    "batch_id": batch_id,
                    "source_id": str(self.source_id),
                    "client_id": self.client_id,
                    "output_path": output_path,
                }),
            )
        except Exception as exc:
            logger.warning("Redis notify failed (non-fatal): %s", exc)
