"""
Kafka event publisher for Layer 1 inter-layer communication.
Publishes to 'layer1.raw.parquet.ready' after each successful sync.
Failures are non-fatal — Redis remains the fallback delivery channel.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from kafka import KafkaProducer
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False
    logger.warning("kafka-python not installed — Kafka event publishing disabled")


class KafkaEventPublisher:
    """
    Thread-safe Kafka producer. Lazy-initializes on first use.
    Producer is reset on error so the next call re-establishes connection.
    """

    def __init__(self, bootstrap_servers: str) -> None:
        self._servers = bootstrap_servers
        self._producer: Optional[Any] = None

    def _ensure_producer(self) -> bool:
        if self._producer is not None:
            return True
        if not _KAFKA_AVAILABLE:
            return False
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=self._servers,
                acks="all",
                retries=3,
                linger_ms=5,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            return True
        except Exception as exc:
            logger.warning("Kafka producer init failed (Kafka may not be running): %s", exc)
            return False

    def publish(self, topic: str, event: dict[str, Any], key: Optional[str] = None) -> bool:
        """
        Publish a JSON event to a Kafka topic.
        Returns True on success, False on any failure. Never raises.
        """
        if not self._ensure_producer():
            return False
        try:
            future = self._producer.send(topic, value=event, key=key)
            self._producer.flush(timeout=5)
            future.get(timeout=5)
            logger.debug("Published to Kafka topic=%s key=%s", topic, key)
            return True
        except Exception as exc:
            logger.warning("Kafka publish failed topic=%s: %s — will retry on next call", topic, exc)
            self._producer = None  # Force re-init on next call
            return False

    def close(self) -> None:
        if self._producer:
            try:
                self._producer.close(timeout=5)
            except Exception:
                pass
            self._producer = None


_publisher: Optional[KafkaEventPublisher] = None


def get_publisher() -> KafkaEventPublisher:
    """Return the module-level publisher singleton. Thread-safe for reads."""
    global _publisher
    if _publisher is None:
        servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        _publisher = KafkaEventPublisher(bootstrap_servers=servers)
    return _publisher
