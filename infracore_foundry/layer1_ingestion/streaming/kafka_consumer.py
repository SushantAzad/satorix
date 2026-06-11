"""
Kafka micro-batch consumer for Layer 1 streaming ingestion.

Each topic maps to one DataSource. Messages are accumulated into micro-batches
by count (default 1000) or time window (default 60 s), whichever comes first.
The resulting DataFrame is processed through the same upload + SyncRun path
as batch ingestion, maintaining full idempotency and lineage continuity.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_KAFKA_AVAILABLE = False
try:
    from kafka import KafkaConsumer as _KafkaConsumer
    from kafka import TopicPartition
    from kafka.errors import KafkaError, NoBrokersAvailable
    _KAFKA_AVAILABLE = True
except ImportError:
    logger.warning("kafka-python not installed — streaming ingestion disabled")


class MicroBatch:
    """Accumulates Kafka messages until size or time threshold is reached."""

    def __init__(self, max_size: int = 1000, max_seconds: float = 60.0) -> None:
        self.max_size = max_size
        self.max_seconds = max_seconds
        self._records: list[dict] = []
        self._start: float = time.monotonic()
        self._lock = threading.Lock()

    def add(self, record: dict) -> bool:
        """Add a record. Returns True if the batch is ready to flush."""
        with self._lock:
            self._records.append(record)
            return self._is_ready()

    def _is_ready(self) -> bool:
        return (
            len(self._records) >= self.max_size
            or (time.monotonic() - self._start) >= self.max_seconds
        )

    def flush(self) -> list[dict]:
        """Return accumulated records and reset the batch."""
        with self._lock:
            records = self._records[:]
            self._records = []
            self._start = time.monotonic()
            return records

    def is_ready(self) -> bool:
        with self._lock:
            return self._is_ready()

    def size(self) -> int:
        with self._lock:
            return len(self._records)


class StreamingIngestionConsumer:
    """
    Consumes messages from a Kafka topic and delivers micro-batches
    to a callback for processing.

    Usage:
        consumer = StreamingIngestionConsumer(
            topic="mca21.company.events",
            bootstrap_servers="kafka:9092",
            group_id="infracore-l1",
            on_batch=process_batch,
        )
        consumer.start()   # non-blocking, runs in background thread
        consumer.stop()    # graceful shutdown
    """

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        group_id: str,
        on_batch: Callable[[list[dict], str, str], None],
        max_batch_size: int = 1000,
        max_batch_seconds: float = 60.0,
        value_deserializer: Optional[Callable] = None,
        auto_offset_reset: str = "earliest",
    ) -> None:
        if not _KAFKA_AVAILABLE:
            raise RuntimeError(
                "kafka-python is required for streaming ingestion. "
                "Install with: pip install kafka-python"
            )
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.on_batch = on_batch
        self.max_batch_size = max_batch_size
        self.max_batch_seconds = max_batch_seconds
        self.auto_offset_reset = auto_offset_reset
        self._value_deserializer = value_deserializer or self._default_deserializer
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._consumer: Optional[Any] = None

    @staticmethod
    def _default_deserializer(raw: bytes) -> dict:
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"_raw": raw.decode("utf-8", errors="replace")}

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"kafka-{self.topic}")
        self._thread.start()
        logger.info("Kafka consumer started: topic=%s group=%s", self.topic, self.group_id)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        logger.info("Kafka consumer stopped: topic=%s", self.topic)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._consume_loop()
            except Exception as exc:
                logger.error("Kafka consumer error on topic %s: %s — retrying in 10s", self.topic, exc)
                time.sleep(10)

    def _consume_loop(self) -> None:
        consumer = _KafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=False,
            value_deserializer=self._value_deserializer,
            consumer_timeout_ms=1000,
        )
        self._consumer = consumer
        batch = MicroBatch(self.max_batch_size, self.max_batch_seconds)
        last_offset: dict[int, int] = {}  # partition → offset

        try:
            while not self._stop_event.is_set():
                try:
                    for msg in consumer:
                        record = msg.value if isinstance(msg.value, dict) else {"value": msg.value}
                        record["_kafka_topic"] = msg.topic
                        record["_kafka_partition"] = msg.partition
                        record["_kafka_offset"] = msg.offset
                        record["_kafka_timestamp"] = msg.timestamp
                        last_offset[msg.partition] = msg.offset
                        ready = batch.add(record)
                        if ready:
                            self._flush_batch(batch, consumer, last_offset.copy())
                except StopIteration:
                    pass

                # Time-based flush even if max_size not reached
                if batch.is_ready() and batch.size() > 0:
                    self._flush_batch(batch, consumer, last_offset.copy())

        finally:
            # Flush remaining records on shutdown
            if batch.size() > 0:
                try:
                    self._flush_batch(batch, consumer, last_offset.copy())
                except Exception as exc:
                    logger.error("Final flush failed on shutdown: %s", exc)
            consumer.close()
            self._consumer = None

    def _flush_batch(
        self,
        batch: MicroBatch,
        consumer: Any,
        last_offsets: dict[int, int],
    ) -> None:
        records = batch.flush()
        if not records:
            return
        offset_str = ",".join(f"p{p}@{o}" for p, o in sorted(last_offsets.items()))
        logger.info(
            "Flushing micro-batch: topic=%s size=%d offsets=[%s]",
            self.topic, len(records), offset_str,
        )
        try:
            self.on_batch(records, self.topic, offset_str)
            # Commit offsets only after successful processing
            consumer.commit()
        except Exception as exc:
            logger.error(
                "Batch processing failed — offsets NOT committed: topic=%s err=%s",
                self.topic, exc,
            )
            # Do not commit — Kafka will re-deliver this batch on next consumer start
