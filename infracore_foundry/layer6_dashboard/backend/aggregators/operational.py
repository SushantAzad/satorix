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
# Service definitions — names must match the frontend's KNOWN_SERVICES list
# ---------------------------------------------------------------------------

_SERVICE_PORT_MAP = {
    "postgres": 5432,
    "redis": 6379,
    "kafka": 9092,
    "elasticsearch": 9200,
    "neo4j-browser": 7474,
    "minio": 9000,
    "airflow": 8080,
    "layer1-api": 8001,
    "layer2-api": 8002,
    "layer3-api": 8003,
    "layer4-api": 8004,
    "layer5-api": 8005,
    "neo4j-bolt": 7687,
    "minio-console": 9001,
}

_SERVICES = [
    {"name": "layer1-api",     "url": f"{settings.layer1_api_url}/ping"},
    {"name": "layer2-api",     "url": f"{settings.layer2_api_url}/health"},
    {"name": "layer3-api",     "url": f"{settings.layer3_api_url}/health"},
    {"name": "layer4-api",     "url": f"{settings.layer4_api_url}/health"},
    {"name": "layer5-api",     "url": f"{settings.layer5_api_url}/health"},
    {"name": "elasticsearch",  "url": "http://elasticsearch:9200"},
    {"name": "neo4j-browser",  "url": "http://neo4j:7474"},
    {"name": "minio",          "url": "http://minio:9000/minio/health/live"},
    {"name": "minio-console",  "url": "http://minio:9001"},
    {"name": "airflow",        "url": "http://airflow-webserver:8080/health"},
    {"name": "postgres",       "url": ""},   # checked via DB pool
    {"name": "redis",          "url": ""},   # checked via redis client
    {"name": "kafka",          "url": ""},   # no HTTP health endpoint
    {"name": "neo4j-bolt",     "url": ""},   # bolt protocol, no HTTP
]

_HEALTH_TIMEOUT = httpx.Timeout(5.0)


async def _check_service(name: str, url: str) -> Dict:
    port = _SERVICE_PORT_MAP.get(name, 0)
    if not url:
        return {
            "name": name,
            "port": port,
            "status": "unknown",
            "response_time_ms": 0,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
            resp = await client.get(url)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        status = "healthy" if resp.status_code < 400 else "degraded"
        return {
            "name": name,
            "port": port,
            "status": status,
            "response_time_ms": elapsed_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.debug("Health check failed for %s: %s", name, exc)
        return {
            "name": name,
            "port": port,
            "status": "unreachable",
            "response_time_ms": elapsed_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Public aggregator functions
# ---------------------------------------------------------------------------

async def get_system_health() -> Dict:
    """Check all services concurrently; return { services: [...], dags: [] }."""
    tasks = [_check_service(svc["name"], svc["url"]) for svc in _SERVICES]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {"services": list(results), "dags": []}


async def get_kafka_topics(clients: LayerClients) -> Dict:
    """
    Attempt to retrieve Kafka topic stats from Layer 3.
    Returns { topics: [...] } suitable for KafkaMonitor.tsx.
    """
    KNOWN_TOPICS = [
        "layer1.raw.parquet.ready",
        "layer2.clean.ready",
        "layer3.ontology.changes",
        "layer3.alerts.created",
        "layer3.ingest.complete",
        "layer4.recompute.triggers",
        "layer4.cache.invalidate",
        "layer5.risk.scores.updated",
        "layer5.predictions.ready",
    ]
    try:
        resp = await clients.l3_client.get("/admin/kafka/topics")
        if resp.status_code < 400:
            data = resp.json()
            topics = data if isinstance(data, list) else data.get("topics", [])
            return {"topics": topics}
    except Exception as exc:
        logger.debug("get_kafka_topics via L3 failed: %s", exc)

    return {
        "topics": [
            {
                "name": t,
                "messages_per_sec": 0,
                "consumer_group_lag": 0,
                "partition_count": 3,
                "retention": "7d",
            }
            for t in KNOWN_TOPICS
        ]
    }


async def get_source_health(clients: LayerClients) -> Dict:
    """Return data source health; wraps result in { sources: [...] }."""
    raw = await clients.get_source_health()
    if raw:
        # Adapt Layer 1 format → frontend SourceData format
        adapted = []
        for s in raw:
            adapted.append({
                "source_name": s.get("sourceName") or s.get("source_name") or s.get("name", "—"),
                "source_type": s.get("source_type") or s.get("sourceType") or "api",
                "client": s.get("client") or s.get("client_id") or s.get("sourceId", "—"),
                "last_sync": s.get("lastSync") or s.get("last_sync") or "—",
                "records_last_run": s.get("records_last_run") or 0,
                "consecutive_failures": s.get("consecutive_failures") or 0,
                "status": s.get("status", "unknown"),
                "sync_history": s.get("sync_history") or [],
            })
        return {"sources": adapted}

    # Synthetic fallback
    return {
        "sources": [
            {
                "source_name": "MCA21 Corporate Registry",
                "source_type": "api",
                "client": "infracore",
                "last_sync": "—",
                "records_last_run": 0,
                "consecutive_failures": 0,
                "status": "unknown",
                "sync_history": [],
            },
            {
                "source_name": "SEBI Regulatory Actions",
                "source_type": "scraper",
                "client": "infracore",
                "last_sync": "—",
                "records_last_run": 0,
                "consecutive_failures": 0,
                "status": "unknown",
                "sync_history": [],
            },
            {
                "source_name": "IBBI Insolvency Proceedings",
                "source_type": "api",
                "client": "infracore",
                "last_sync": "—",
                "records_last_run": 0,
                "consecutive_failures": 0,
                "status": "unknown",
                "sync_history": [],
            },
            {
                "source_name": "RERA Project Registry",
                "source_type": "api",
                "client": "infracore",
                "last_sync": "—",
                "records_last_run": 0,
                "consecutive_failures": 0,
                "status": "unknown",
                "sync_history": [],
            },
        ]
    }


async def get_ingestion_queue(clients: LayerClients) -> Dict:
    """Return pipeline batch status as { batches: [...] }."""
    return {"batches": []}


async def get_ontology_health(clients: LayerClients) -> Dict:
    """Return ontology health with real schema types and per-type instance counts."""
    from core.database import async_session_maker
    from sqlalchemy.sql import text as sql_text

    schema_types: list = []
    total_objects = 0
    total_links = 0
    property_coverage_by_type: Dict = {}

    try:
        schema_resp, ontology_resp = await asyncio.gather(
            clients.l3_client.get("/schema/object-types"),
            clients.l3_client.get("/health/ontology"),
            return_exceptions=True,
        )
        if not isinstance(schema_resp, Exception) and schema_resp.status_code < 400:
            schema_types = schema_resp.json().get("object_types", [])
        if not isinstance(ontology_resp, Exception) and ontology_resp.status_code < 400:
            od = ontology_resp.json()
            total_objects = od.get("total_objects", 0)
            total_links = od.get("total_links", 0)
            property_coverage_by_type = od.get("property_coverage", {})
    except Exception as exc:
        logger.debug("get_ontology_health L3 fetch failed: %s", exc)

    # Per-type instance counts from postgres ontology_objects table
    type_counts: Dict[str, Dict] = {}
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                sql_text(
                    "SELECT object_type, COUNT(*) AS cnt, MAX(updated_at) AS last_mod "
                    "FROM ontology_objects WHERE is_deleted = false GROUP BY object_type"
                )
            )
            for row in result.fetchall():
                type_counts[row.object_type] = {
                    "count": int(row.cnt),
                    "last_modified": row.last_mod.isoformat() if row.last_mod else "—",
                }
    except Exception as exc:
        logger.debug("get_ontology_health postgres count failed: %s", exc)

    object_types = []
    for st in schema_types:
        api_name = st.get("api_name", "")
        raw_props = st.get("properties") or []
        type_coverage = property_coverage_by_type.get(api_name, {})
        mapped_props = [
            {
                "property_name": p.get("name", ""),
                "type": p.get("type", "str"),
                "required": bool(p.get("required", p.get("immutable", False))),
                "completeness_pct": type_coverage.get(p.get("name", ""), 0),
                "source": "schema_registry",
            }
            for p in raw_props
            if isinstance(p, dict) and p.get("name")
        ]
        object_types.append({
            "name": api_name,
            "display_name": st.get("display_name", api_name.replace("_", " ").title()),
            "property_count": len(mapped_props),
            "instance_count": type_counts.get(api_name, {}).get("count", 0),
            "last_modified": type_counts.get(api_name, {}).get("last_modified", "—"),
            "properties": mapped_props,
        })

    return {
        "health_score": 100 if total_objects > 0 else 0,
        "object_types": object_types,
        "total_objects": total_objects,
        "total_links": total_links,
        "property_coverage": [],
        "orphan_counts": [],
        "impossible_states": [],
        "duplicate_candidates": [],
        "dead_letter_queue": [],
        "status": "ok" if total_objects > 0 else "empty",
    }


def _normalize_model(m: Dict) -> Dict:
    """Normalize a model dict from Layer 5 to the dashboard schema."""
    eval_metrics = m.get("evaluation_metrics") or {}
    auc_roc = (
        m.get("auc_roc")
        or m.get("auc_roc_score")
        or eval_metrics.get("auc_roc")
        or eval_metrics.get("auc_roc_score")
        or eval_metrics.get("roc_auc")
        or 0
    )
    total_predictions = (
        m.get("total_predictions")
        or m.get("predictions_total")
        or m.get("predictions_count")
        or m.get("predictions_today")
        or 0
    )
    return {
        "name": m.get("name") or m.get("model_id") or m.get("model_name", "unknown"),
        "version": m.get("version") or m.get("model_version", "—"),
        "last_trained": m.get("last_trained") or m.get("training_date") or m.get("trained_at") or "—",
        "total_predictions": total_predictions,
        "auc_roc": auc_roc,
        "status": m.get("status", "unknown"),
        "model_status": m.get("model_status") or ("Active" if m.get("status") == "active" else "Unknown"),
    }


async def get_model_performance(clients: LayerClients) -> Dict:
    """Call Layer 5 /observability/metrics for ML model stats."""
    result = await clients.get_model_performance()
    if result and result.get("models"):
        normalized_models = [_normalize_model(m) for m in result["models"]]
        return {**result, "models": normalized_models}

    return {
        "models": [
            {
                "name": "cirp_precursor",
                "version": "v2.1.0",
                "last_trained": "—",
                "total_predictions": 0,
                "auc_roc": 0,
                "status": "unknown",
                "model_status": "Active",
            },
            {
                "name": "project_completion",
                "version": "v1.3.2",
                "last_trained": "—",
                "total_predictions": 0,
                "auc_roc": 0,
                "status": "unknown",
                "model_status": "Active",
            },
            {
                "name": "regulatory_likelihood",
                "version": "v1.0.5",
                "last_trained": "—",
                "total_predictions": 0,
                "auc_roc": 0,
                "status": "unknown",
                "model_status": "Active",
            },
        ],
        "llm": {
            "calls_today": 0,
            "cache_hit_rate": 0,
            "avg_latency_ms": 0,
            "usage_by_workflow": [
                {"workflow": "narrative", "calls": 0, "tokens": 0},
                {"workflow": "report", "calls": 0, "tokens": 0},
                {"workflow": "agent", "calls": 0, "tokens": 0},
            ],
        },
    }


async def get_alert_analytics(clients: LayerClients, days: int = 30) -> Dict:
    """
    Aggregate alert volume over the past *days* days from Layer 3.
    Returns format matching AlertAnalytics.tsx.
    """
    try:
        resp = await clients.l3_client.get(
            "/intelligence/alerts/analytics", params={"days": days}
        )
        if resp.status_code < 400:
            data = resp.json()
            # If Layer 3 already returns the right format, use it
            if "daily_alerts" in data:
                return data
    except Exception as exc:
        logger.debug("get_alert_analytics failed: %s", exc)

    # Fallback: fetch raw alerts and compute locally
    raw = await clients.get_alerts(limit=500)

    daily: Dict[str, Dict[str, int]] = {}
    severity_totals: Dict[str, int] = {}
    type_totals: Dict[str, int] = {}
    acknowledged = 0
    unacknowledged = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for alert in raw:
        ts_raw = alert.get("created_at") or alert.get("timestamp") or ""
        sev = (alert.get("severity") or "LOW").upper()
        alert_type = alert.get("alertType") or alert.get("alert_type") or "UNKNOWN"
        is_acked = alert.get("isAcknowledged") or alert.get("is_acknowledged") or False

        if is_acked:
            acknowledged += 1
        else:
            unacknowledged += 1

        type_totals[alert_type] = type_totals.get(alert_type, 0) + 1

        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts < cutoff:
                continue
            day_key = ts.date().isoformat()
            daily.setdefault(day_key, {"critical": 0, "high": 0, "medium": 0, "low": 0})
            sev_key = sev.lower()
            if sev_key in daily[day_key]:
                daily[day_key][sev_key] += 1
        except (ValueError, AttributeError):
            pass

    daily_list = [{"date": d, **counts} for d, counts in sorted(daily.items())]
    alerts_by_type = [{"type": t, "count": c} for t, c in sorted(type_totals.items(), key=lambda x: -x[1])]

    return {
        "daily_alerts": daily_list,
        "alerts_by_type": alerts_by_type,
        "acknowledged": acknowledged,
        "unacknowledged": unacknowledged,
        "top_entities": [],
    }
