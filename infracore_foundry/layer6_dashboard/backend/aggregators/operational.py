"""
Operational Aggregator — assembles system health, pipeline, and observability data
for the operational dashboard.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Service definitions for health checks
# ---------------------------------------------------------------------------

_SERVICES = [
    {"name": "Layer 1 — Ingestion", "url": f"{settings.layer1_api_url}/health"},
    {"name": "Layer 2 — Pipeline", "url": f"{settings.layer2_api_url}/health"},
    {"name": "Layer 3 — Ontology", "url": f"{settings.layer3_api_url}/health"},
    {"name": "Layer 4 — Graph Intelligence", "url": f"{settings.layer4_api_url}/health"},
    {"name": "Layer 5 — ML Analytics", "url": f"{settings.layer5_api_url}/health"},
    {"name": "Layer 6 — Dashboard API", "url": "http://localhost:8006/health"},
    {"name": "PostgreSQL", "url": ""},  # checked separately
    {"name": "Redis", "url": ""},  # checked separately
    {"name": "Kafka", "url": ""},  # checked separately
]

_HEALTH_TIMEOUT = httpx.Timeout(5.0)


async def _check_service(name: str, url: str) -> Dict:
    """Ping a single service health endpoint and return status dict."""
    if not url:
        return {
            "serviceName": name,
            "status": "unknown",
            "responseTimeMs": -1,
            "lastChecked": datetime.now(timezone.utc).isoformat(),
        }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
            resp = await client.get(url)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        status = "healthy" if resp.status_code < 400 else "degraded"
        return {
            "serviceName": name,
            "status": status,
            "responseTimeMs": elapsed_ms,
            "lastChecked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.debug("Health check failed for %s: %s", name, exc)
        return {
            "serviceName": name,
            "status": "unreachable",
            "responseTimeMs": elapsed_ms,
            "lastChecked": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Public aggregator functions
# ---------------------------------------------------------------------------

async def get_system_health() -> List[Dict]:
    """Check all Docker services concurrently and return status grid."""
    tasks = [_check_service(svc["name"], svc["url"]) for svc in _SERVICES]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


async def get_kafka_topics(clients: LayerClients) -> List[Dict]:
    """
    Attempt to retrieve Kafka topic stats from Layer 3.
    Returns a synthetic list if unavailable.
    """
    try:
        resp = await clients.l3_client.get("/admin/kafka/topics")
        if resp.status_code < 400:
            data = resp.json()
            return data if isinstance(data, list) else data.get("topics", [])
    except Exception as exc:
        logger.debug("get_kafka_topics via L3 failed: %s", exc)

    # Synthetic fallback
    return [
        {
            "topic": "layer1.raw.mca",
            "partitions": 3,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
        {
            "topic": "layer2.cleaned.entities",
            "partitions": 3,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
        {
            "topic": "layer3.ontology.changes",
            "partitions": 3,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
        {
            "topic": "layer5.risk.scores.updated",
            "partitions": 2,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
        {
            "topic": "layer5.predictions.ready",
            "partitions": 2,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
        {
            "topic": "layer3.alerts.created",
            "partitions": 2,
            "messagesPerSecond": 0,
            "lag": 0,
            "status": "unknown",
        },
    ]


async def get_source_health(clients: LayerClients) -> List[Dict]:
    """Return data source health from Layer 1."""
    sources = await clients.get_source_health()
    if sources:
        return sources
    # Fallback — synthetic sources
    return [
        {"sourceId": "mca-api", "sourceName": "MCA API", "status": "unknown", "lastSync": None},
        {"sourceId": "rera-api", "sourceName": "RERA API", "status": "unknown", "lastSync": None},
        {"sourceId": "sebi-api", "sourceName": "SEBI API", "status": "unknown", "lastSync": None},
        {"sourceId": "gst-api", "sourceName": "GST API", "status": "unknown", "lastSync": None},
        {"sourceId": "nclt-scraper", "sourceName": "NCLT Scraper", "status": "unknown", "lastSync": None},
    ]


async def get_ingestion_queue(clients: LayerClients) -> Dict:
    """Assemble pipeline status from Layer 1 + Layer 2 + Layer 3."""
    try:
        l1_resp, l3_resp = await asyncio.gather(
            clients.l1_client.get("/api/v1/pipeline/status"),
            clients.l3_client.get("/pipeline/status"),
            return_exceptions=True,
        )
        l1_data: Any = {}
        l3_data: Any = {}
        if not isinstance(l1_resp, Exception) and l1_resp.status_code < 400:
            l1_data = l1_resp.json()
        if not isinstance(l3_resp, Exception) and l3_resp.status_code < 400:
            l3_data = l3_resp.json()

        return {
            "layer1": l1_data,
            "layer3": l3_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.debug("get_ingestion_queue failed: %s", exc)
        return {
            "layer1": {},
            "layer3": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "Pipeline status unavailable",
        }


async def get_ontology_health(clients: LayerClients) -> Dict:
    """Call Layer 3 /health for ontology coverage and quality metrics."""
    try:
        resp = await clients.l3_client.get("/health")
        if resp.status_code < 400:
            return resp.json()
    except Exception as exc:
        logger.debug("get_ontology_health failed: %s", exc)

    return {
        "status": "unknown",
        "nodeCount": None,
        "edgeCount": None,
        "entityTypes": [],
        "coveragePercent": None,
        "lastUpdated": None,
    }


async def get_model_performance(clients: LayerClients) -> Dict:
    """Call Layer 5 /observability/metrics for ML model stats."""
    result = await clients.get_model_performance()
    if result:
        return result
    return {
        "status": "unknown",
        "models": [],
        "accuracy": None,
        "lastRetrained": None,
        "predictionCount": None,
    }


async def get_alert_analytics(clients: LayerClients, days: int = 30) -> Dict:
    """
    Aggregate alert volume over the past *days* days from Layer 3.
    Returns daily counts grouped by severity.
    """
    try:
        resp = await clients.l3_client.get(
            "/intelligence/alerts/analytics", params={"days": days}
        )
        if resp.status_code < 400:
            return resp.json()
    except Exception as exc:
        logger.debug("get_alert_analytics failed: %s", exc)

    # Fallback: fetch raw alerts and compute locally
    raw = await clients.get_alerts(limit=500)
    if not raw:
        return {"days": days, "daily": [], "bySeverity": {}}

    # Build daily buckets
    daily: Dict[str, Dict[str, int]] = {}
    severity_totals: Dict[str, int] = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for alert in raw:
        ts_raw = alert.get("created_at") or alert.get("timestamp") or ""
        sev = alert.get("severity", "LOW").upper()
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts < cutoff:
                continue
            day_key = ts.date().isoformat()
            daily.setdefault(day_key, {})
            daily[day_key][sev] = daily[day_key].get(sev, 0) + 1
            severity_totals[sev] = severity_totals.get(sev, 0) + 1
        except (ValueError, AttributeError):
            pass

    daily_list = [{"date": d, **counts} for d, counts in sorted(daily.items())]
    return {"days": days, "daily": daily_list, "bySeverity": severity_totals}
