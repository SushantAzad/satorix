"""
Real-time risk score delta stream.
Consumes layer3.ontology.changes, recomputes ML risk score for affected entities,
and publishes deltas to layer5.risk.scores.updated.
"""
import json
import logging
import threading
import time

from core.kafka_client import (
    make_consumer, publish,
    TOPIC_L3_ONTOLOGY_CHANGES, TOPIC_RISK_SCORES_UPDATED,
)

logger = logging.getLogger(__name__)

# Features that, when changed, should trigger ML risk recomputation
RISK_TRIGGERING_PROPERTIES = {
    "status", "riskScore", "riskFlags",
    "debtEquityRatio", "currentRatio",
    "directorCount", "isOffshore",
    "disqualificationStatus",
}

_running = False
_thread: threading.Thread | None = None


def _process_change(message: dict) -> None:
    object_type = message.get("object_type", "")
    entity_id = message.get("primary_key") or message.get("entity_id")
    changed_props = set(message.get("changed_properties", {}).keys())

    if not entity_id:
        return
    if not changed_props.intersection(RISK_TRIGGERING_PROPERTIES):
        return
    if object_type not in ("company", "Company"):
        return

    # Publish trigger for downstream consumers (L6 dashboard cache invalidation)
    publish(TOPIC_RISK_SCORES_UPDATED, {
        "entity_type": "Company",
        "entity_id": entity_id,
        "trigger": "ontology_change",
        "changed_properties": list(changed_props),
        "timestamp": time.time(),
    }, key=entity_id)


def _run_loop() -> None:
    global _running
    consumer = make_consumer([TOPIC_L3_ONTOLOGY_CHANGES], group_id="l5-risk-delta-stream")
    logger.info("Risk delta stream started, consuming %s", TOPIC_L3_ONTOLOGY_CHANGES)
    try:
        while _running:
            messages = consumer.poll(timeout_ms=1000)
            for tp, records in messages.items():
                for record in records:
                    try:
                        _process_change(record.value)
                    except Exception as exc:
                        logger.error("Risk delta processing error: %s", exc)
    finally:
        consumer.close()
        logger.info("Risk delta stream stopped")


def start() -> None:
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_run_loop, daemon=True, name="l5-risk-delta")
    _thread.start()


def stop() -> None:
    global _running
    _running = False
