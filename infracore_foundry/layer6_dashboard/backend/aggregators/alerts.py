"""
Alerts Aggregator — fetches, enriches, sorts, and filters alerts from Layer 3.
"""
import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_rank(alert: Dict) -> int:
    return _SEVERITY_ORDER.get(alert.get("severity", "INFO").upper(), 99)


def _sort_alerts(alerts: List[Dict]) -> List[Dict]:
    """
    Sort: unacknowledged first, then by severity (CRITICAL→LOW), then newest first.
    """
    def sort_key(a: Dict):
        ack = 0 if not a.get("acknowledged", False) else 1
        sev = _severity_rank(a)
        ts_raw = a.get("created_at") or a.get("timestamp") or ""
        # Reverse-sort by timestamp — negate by using empty string sorts later
        return (ack, sev, ts_raw)

    return sorted(alerts, key=sort_key)


def _matches_filters(
    alert: Dict,
    severity: Optional[str],
    alert_type: Optional[str],
    entity_type: Optional[str],
    acknowledged: Optional[bool],
    date_from: Optional[date],
    date_to: Optional[date],
) -> bool:
    if severity and alert.get("severity", "").upper() != severity.upper():
        return False
    if alert_type and alert.get("alert_type", "").upper() != alert_type.upper():
        return False
    if entity_type and alert.get("entity_type", "").lower() != entity_type.lower():
        return False
    if acknowledged is not None and bool(alert.get("acknowledged")) != acknowledged:
        return False
    if date_from or date_to:
        ts_raw = alert.get("created_at") or alert.get("timestamp") or ""
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).date()
                if date_from and ts < date_from:
                    return False
                if date_to and ts > date_to:
                    return False
            except (ValueError, AttributeError):
                pass
    return True


# ---------------------------------------------------------------------------
# Public aggregator functions
# ---------------------------------------------------------------------------

async def get_alert_list(
    clients: LayerClients,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict:
    """
    Return a filtered, sorted AlertListResponse dict.
    """
    raw_alerts = await clients.get_alerts(
        severity=severity,
        limit=200,  # Fetch more than needed so we can filter locally
    )

    # Apply local filters (L3 may not support all filter params)
    filtered = [
        a for a in raw_alerts
        if _matches_filters(a, severity, alert_type, entity_type, acknowledged, date_from, date_to)
    ]

    sorted_alerts = _sort_alerts(filtered)

    # Compute summary counts
    unacknowledged = sum(1 for a in sorted_alerts if not a.get("acknowledged", False))
    critical_count = sum(1 for a in sorted_alerts if a.get("severity", "").upper() == "CRITICAL")
    high_count = sum(1 for a in sorted_alerts if a.get("severity", "").upper() == "HIGH")

    page_alerts = sorted_alerts[offset: offset + limit]

    return {
        "alerts": page_alerts,
        "total": len(sorted_alerts),
        "unacknowledged": unacknowledged,
        "critical_count": critical_count,
        "high_count": high_count,
    }


async def get_alert_summary(clients: LayerClients) -> Dict:
    """
    Return aggregate counts: total, critical, high, medium, low, unacknowledged, new_today.
    """
    raw_alerts = await clients.get_alerts(limit=500)

    today = datetime.now(timezone.utc).date()

    total = len(raw_alerts)
    unacknowledged = sum(1 for a in raw_alerts if not a.get("acknowledged", False))

    counts: Dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    new_today = 0

    for alert in raw_alerts:
        sev = alert.get("severity", "LOW").upper()
        if sev in counts:
            counts[sev] += 1

        ts_raw = alert.get("created_at") or alert.get("timestamp") or ""
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).date()
                if ts == today:
                    new_today += 1
            except (ValueError, AttributeError):
                pass

    return {
        "total": total,
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
        "unacknowledged": unacknowledged,
        "new_today": new_today,
    }


async def get_alert_detail(clients: LayerClients, alert_id: str) -> Optional[Dict]:
    """
    Return a detailed view of a single alert, enriched with entity context.
    """
    alert = await clients.get_alert(alert_id)
    if alert is None:
        return None

    # Try to enrich with entity profile summary
    entity_type = alert.get("entity_type")
    entity_id = alert.get("entity_id")
    entity_context: Optional[Dict] = None
    if entity_type and entity_id:
        entity_context = await clients.get_entity(entity_type, entity_id)

    shap_explanation = alert.get("shap_explanation") or alert.get("explanation")
    action_log = alert.get("action_log", [])

    return {
        **alert,
        "entityContext": entity_context,
        "shapExplanation": shap_explanation,
        "actionLog": action_log,
    }
