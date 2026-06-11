"""
Alert trigger stream.
Subscribes to layer5.risk.scores.updated.
When any entity's ML risk score crosses a configured threshold,
immediately fires a create_alert call to Layer 3.
"""
import logging
import threading
import time

import httpx

from core.config import settings
from core.kafka_client import make_consumer, TOPIC_RISK_SCORES_UPDATED

logger = logging.getLogger(__name__)

DEFAULT_ALERT_THRESHOLD = 85.0

_running = False
_thread: threading.Thread | None = None


def _fire_alert(entity_id: str, entity_type: str, risk_score: float) -> None:
    try:
        import requests
        resp = requests.post(
            f"{settings.layer3_api_url}/api/v1/actions/create-alert",
            json={
                "entity_id": entity_id,
                "alert_type": "ML_HIGH_RISK",
                "message": f"ML model risk score {risk_score:.1f}% crosses threshold — immediate review required",
                "actor_id": "l5_alert_stream",
            },
            timeout=5,
        )
        if resp.status_code in (200, 201):
            logger.info("Alert fired for %s (score=%.1f)", entity_id, risk_score)
    except Exception as exc:
        logger.warning("Alert fire failed for %s: %s", entity_id, exc)


def _run_loop() -> None:
    global _running
    consumer = make_consumer([TOPIC_RISK_SCORES_UPDATED], group_id="l5-alert-trigger-stream")
    alerted_this_run: set[str] = set()  # dedup within a run window

    logger.info("Alert trigger stream started")
    try:
        while _running:
            messages = consumer.poll(timeout_ms=1000)
            for tp, records in messages.items():
                for record in records:
                    try:
                        msg = record.value
                        entity_id = msg.get("entity_id", "")
                        score = float(msg.get("ml_risk_score", msg.get("prediction_value", 0)) or 0)
                        if score >= DEFAULT_ALERT_THRESHOLD and entity_id not in alerted_this_run:
                            _fire_alert(entity_id, msg.get("entity_type", "Company"), score)
                            alerted_this_run.add(entity_id)
                    except Exception as exc:
                        logger.error("Alert trigger error: %s", exc)
            # Reset dedup set every hour
            if int(time.time()) % 3600 < 2:
                alerted_this_run.clear()
    finally:
        consumer.close()


def start() -> None:
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_run_loop, daemon=True, name="l5-alert-trigger")
    _thread.start()


def stop() -> None:
    global _running
    _running = False
