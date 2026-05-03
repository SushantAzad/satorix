"""
Kafka publisher for Layer 3 ontology change events.
Publishes to 'layer3.ontology.changes' (per-object, high-frequency) and
'layer3.ingest.complete' (per-batch, low-frequency) for Layer 4 consumption.

Uses acks=0 for ontology.changes (fire-and-forget cache invalidation)
and acks='all' for ingest.complete (downstream trigger — must not be lost).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CHANGES_TOPIC = "layer3.ontology.changes"
_INGEST_COMPLETE_TOPIC = "layer3.ingest.complete"

try:
    from kafka import KafkaProducer
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False
    logger.debug("kafka-python not installed — Layer 3 Kafka publishing disabled")


class _OntologyKafkaPublisher:
    """
    Module-level singleton publisher. Two producers:
    - _ff_producer: acks=0, used for high-frequency ontology.changes (cache invalidation)
    - _ack_producer: acks='all', used for ingest.complete (reliable delivery)
    """

    def __init__(self) -> None:
        self._servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        self._ff_producer: Optional[Any] = None   # fire-and-forget
        self._ack_producer: Optional[Any] = None  # acknowledged

    def _get_ff(self) -> Optional[Any]:
        if self._ff_producer is not None:
            return self._ff_producer
        if not _KAFKA_AVAILABLE:
            return None
        try:
            self._ff_producer = KafkaProducer(
                bootstrap_servers=self._servers,
                acks=0,
                linger_ms=100,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            )
        except Exception as exc:
            logger.debug("Kafka ff-producer init failed: %s", exc)
        return self._ff_producer

    def _get_ack(self) -> Optional[Any]:
        if self._ack_producer is not None:
            return self._ack_producer
        if not _KAFKA_AVAILABLE:
            return None
        try:
            self._ack_producer = KafkaProducer(
                bootstrap_servers=self._servers,
                acks="all",
                retries=3,
                linger_ms=5,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            )
        except Exception as exc:
            logger.debug("Kafka ack-producer init failed: %s", exc)
        return self._ack_producer

    def emit_change(
        self,
        event_type: str,
        object_type: str,
        object_id: str,
        changed_fields: Optional[list[str]] = None,
    ) -> None:
        """Fire-and-forget: publish to layer3.ontology.changes for Layer 4 cache invalidation."""
        producer = self._get_ff()
        if producer is None:
            return
        try:
            producer.send(
                _CHANGES_TOPIC,
                value={
                    "event_type": event_type,
                    "object_type": object_type,
                    "object_id": object_id,
                    "changed_fields": changed_fields or [],
                },
            )
            # No flush — use linger_ms batching for throughput
        except Exception as exc:
            logger.debug("Kafka ontology.changes publish failed (non-fatal): %s", exc)
            self._ff_producer = None

    def emit_ingest_complete(self, payload: dict[str, Any]) -> bool:
        """Acknowledged publish to layer3.ingest.complete for Layer 4 batch recompute."""
        producer = self._get_ack()
        if producer is None:
            return False
        try:
            future = producer.send(_INGEST_COMPLETE_TOPIC, value=payload)
            producer.flush(timeout=5)
            future.get(timeout=5)
            logger.info("Published layer3.ingest.complete: client=%s", payload.get("client_id"))
            return True
        except Exception as exc:
            logger.warning("Kafka ingest.complete publish failed (non-fatal): %s", exc)
            self._ack_producer = None
            return False


_publisher: Optional[_OntologyKafkaPublisher] = None


def get_ontology_publisher() -> _OntologyKafkaPublisher:
    """Return the module-level singleton (created once, never replaced)."""
    global _publisher
    if _publisher is None:
        _publisher = _OntologyKafkaPublisher()
    return _publisher
