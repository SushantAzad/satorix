"""
Kafka → WebSocket bridge — consumes Layer 3/5 Kafka topics in a background asyncio
task and pushes events to subscribed WebSocket clients via the ConnectionManager.

Uses confluent_kafka.Consumer in a thread-pool executor so the asyncio event loop
is never blocked.
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Topics this consumer bridges to WebSocket clients
_TOPICS = [
    "layer3.ontology.changes",
    "layer3.alerts.created",
    "layer5.risk.scores.updated",
    "layer5.predictions.ready",
]

_POLL_TIMEOUT_S = 1.0
_RECONNECT_DELAY_S = 5.0

# Thread pool for blocking Kafka I/O
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kafka-consumer")

_consumer_running: bool = False


def _make_consumer():
    """Create and return a confluent_kafka.Consumer, or None if Kafka is unavailable."""
    try:
        from confluent_kafka import Consumer, KafkaError  # noqa: F401
        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": "layer6-websocket-bridge",
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
                "session.timeout.ms": 10_000,
            }
        )
        consumer.subscribe(_TOPICS)
        logger.info("Kafka consumer subscribed to topics: %s", _TOPICS)
        return consumer
    except Exception as exc:
        logger.warning("Could not initialise Kafka consumer: %s", exc)
        return None


def _poll_once(consumer) -> Optional[dict]:
    """
    Poll Kafka for one message (blocking, runs in thread pool).
    Returns a parsed dict or None.
    """
    try:
        msg = consumer.poll(timeout=_POLL_TIMEOUT_S)
        if msg is None:
            return None
        if msg.error():
            from confluent_kafka import KafkaError
            if msg.error().code() == KafkaError._PARTITION_EOF:
                return None
            logger.warning("Kafka error: %s", msg.error())
            return None
        value = msg.value()
        if value:
            return {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
                "payload": json.loads(value.decode("utf-8")),
            }
    except Exception as exc:
        logger.warning("Kafka poll error: %s", exc)
    return None


async def _dispatch_message(topic: str, payload: dict) -> None:
    """Route a parsed Kafka message to the appropriate WebSocket broadcast."""
    from websocket.manager import manager  # local import to avoid circular

    entity_type: str = (
        payload.get("entityType")
        or payload.get("entity_type")
        or payload.get("type")
        or "unknown"
    )
    entity_id: str = (
        payload.get("entityId")
        or payload.get("entity_id")
        or payload.get("id")
        or ""
    )

    if "alerts" in topic:
        await manager.broadcast_alert(payload)
        logger.debug("Kafka → broadcast alert: %s", payload.get("alert_id"))

    elif "ontology.changes" in topic:
        if entity_type and entity_id:
            await manager.broadcast_entity_update(
                entity_type,
                entity_id,
                {"event": "ontology_change", **payload},
            )

    elif "risk.scores" in topic:
        if entity_type and entity_id:
            await manager.broadcast_entity_update(
                entity_type,
                entity_id,
                {"event": "risk_update", "riskScore": payload.get("risk_score"), **payload},
            )

    elif "predictions.ready" in topic:
        if entity_type and entity_id:
            await manager.broadcast_entity_update(
                entity_type,
                entity_id,
                {"event": "prediction_ready", **payload},
            )


async def run_kafka_consumer() -> None:
    """
    Long-running asyncio coroutine that polls Kafka and dispatches events.
    Reconnects with back-off if Kafka is unavailable.
    """
    global _consumer_running
    _consumer_running = True

    loop = asyncio.get_event_loop()

    while _consumer_running:
        consumer = await loop.run_in_executor(_executor, _make_consumer)

        if consumer is None:
            logger.info(
                "Kafka unavailable — retrying in %ss.", _RECONNECT_DELAY_S
            )
            await asyncio.sleep(_RECONNECT_DELAY_S)
            continue

        logger.info("Kafka consumer running.")
        try:
            while _consumer_running:
                raw = await loop.run_in_executor(_executor, _poll_once, consumer)
                if raw:
                    await _dispatch_message(raw["topic"], raw["payload"])
                else:
                    # Yield control back to the event loop briefly
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled.")
            break
        except Exception as exc:
            logger.warning("Kafka consumer error: %s — reconnecting in %ss.", exc, _RECONNECT_DELAY_S)
        finally:
            try:
                consumer.close()
            except Exception:
                pass

        if _consumer_running:
            await asyncio.sleep(_RECONNECT_DELAY_S)

    _consumer_running = False
    logger.info("Kafka consumer stopped.")


def stop_kafka_consumer() -> None:
    """Signal the consumer loop to stop (call on application shutdown)."""
    global _consumer_running
    _consumer_running = False
