"""
NetworkCache — thin wrapper that invalidates l4:network_* keys when
Layer 3 emits ontology-change events on Kafka.
"""
import asyncio
import json
import logging
from typing import Optional

from kafka import KafkaConsumer

from core.redis_client import cache_delete_pattern
from core.config import settings

logger = logging.getLogger(__name__)

_consumer_task: Optional[asyncio.Task] = None


async def start_cache_invalidator() -> None:
    global _consumer_task
    _consumer_task = asyncio.create_task(_invalidation_loop())
    logger.info("Layer 4 cache invalidator started (topic: layer3.ontology.changes)")


async def stop_cache_invalidator() -> None:
    global _consumer_task
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None


async def _invalidation_loop() -> None:
    loop = asyncio.get_event_loop()
    consumer = await loop.run_in_executor(None, _make_consumer)
    try:
        while True:
            msgs = await loop.run_in_executor(None, lambda: consumer.poll(timeout_ms=500))
            for tp, records in msgs.items():
                for record in records:
                    await _handle_change(record.value)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        consumer.close()


def _make_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        "layer3.ontology.changes",
        "layer3.ingest.complete",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )


async def _handle_change(event: dict) -> None:
    entity_id = event.get("object_id") or event.get("entity_id")
    if not entity_id:
        return
    deleted = await cache_delete_pattern(f"l4:*:{entity_id}*")
    deleted += await cache_delete_pattern(f"l4:network_expand:*")
    if deleted:
        logger.debug("Cache invalidated %d keys for entity %s", deleted, entity_id)
