"""
Trend update stream.
Accumulates property changes from layer3.ontology.changes into 15-minute windows.
At each window boundary, recomputes trend metrics for changed entities.
"""
import asyncio
import logging
import threading
import time
from collections import defaultdict

from core.kafka_client import make_consumer, publish, TOPIC_L3_ONTOLOGY_CHANGES, TOPIC_TRENDS_DETECTED

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 900  # 15 minutes

TREND_METRICS = {
    "Company": ["layer3_risk_score", "current_ratio", "debt_equity_ratio", "regulatory_action_count_12m"],
}

_running = False
_thread: threading.Thread | None = None
_pending: dict[str, set] = defaultdict(set)  # entity_id → set of changed metrics
_last_flush = time.time()


def _flush_window() -> None:
    global _last_flush, _pending
    if not _pending:
        _last_flush = time.time()
        return

    batch = dict(_pending)
    _pending = defaultdict(set)
    _last_flush = time.time()

    for entity_id in batch:
        publish(TOPIC_TRENDS_DETECTED, {
            "entity_type": "Company",
            "entity_id": entity_id,
            "trigger": "window_flush",
            "timestamp": time.time(),
        }, key=entity_id)

    logger.debug("Trend window flushed: %d entities", len(batch))


def _run_loop() -> None:
    global _running
    consumer = make_consumer([TOPIC_L3_ONTOLOGY_CHANGES], group_id="l5-trend-update-stream")
    logger.info("Trend update stream started (window=%ds)", WINDOW_SECONDS)
    try:
        while _running:
            messages = consumer.poll(timeout_ms=5000)
            for tp, records in messages.items():
                for record in records:
                    try:
                        msg = record.value
                        entity_id = msg.get("primary_key") or msg.get("entity_id", "")
                        if entity_id:
                            _pending[entity_id].update(msg.get("changed_properties", {}).keys())
                    except Exception as exc:
                        logger.error("Trend stream error: %s", exc)

            if time.time() - _last_flush >= WINDOW_SECONDS:
                _flush_window()
    finally:
        consumer.close()


def start() -> None:
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_run_loop, daemon=True, name="l5-trend-update")
    _thread.start()


def stop() -> None:
    global _running
    _running = False
