"""Kafka producer + consumer helpers for Layer 5."""
import json
import logging
from typing import Callable, Optional

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

from .config import settings

logger = logging.getLogger(__name__)

# Layer 5 topics (producers)
TOPIC_RISK_SCORES_UPDATED = "layer5.risk.scores.updated"
TOPIC_PREDICTIONS_READY = "layer5.predictions.ready"
TOPIC_BENCHMARKS_COMPUTED = "layer5.benchmarks.computed"
TOPIC_TRENDS_DETECTED = "layer5.trends.detected"

# Consumed topics from upstream layers
TOPIC_L3_ONTOLOGY_CHANGES = "layer3.ontology.changes"
TOPIC_L3_INGEST_COMPLETE = "layer3.ingest.complete"
TOPIC_L4_INTELLIGENCE_READY = "layer4.intelligence.ready"

_producer: Optional[KafkaProducer] = None


def get_producer() -> KafkaProducer:
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retries=3,
        )
    return _producer


def publish(topic: str, value: dict, key: Optional[str] = None) -> None:
    try:
        get_producer().send(topic, value=value, key=key)
    except KafkaError as exc:
        logger.error("Kafka publish failed topic=%s: %s", topic, exc)


def close_producer() -> None:
    global _producer
    if _producer:
        _producer.flush()
        _producer.close()
        _producer = None


def make_consumer(topics: list[str], group_id: Optional[str] = None) -> KafkaConsumer:
    return KafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id or settings.kafka_group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
