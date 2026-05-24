"""
Entity Profile Aggregator — fetches data from Layers 3, 4, and 5 concurrently
and assembles a unified EntityProfileResponse for the dashboard.

Falls back to demo/mock data when upstream layers are unavailable so the UI
always has something meaningful to display.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo / fallback data for well-known CIN prefixes
# ---------------------------------------------------------------------------

_DEMO_COMPANIES: Dict[str, Dict] = {
    "L45201MH": {
        "name": "Reliance Industries Limited",
        "cin": "L45201MH1973PLC019786",
        "status": "ACTIVE",
        "incorporation_date": "1973-05-08",
        "registered_state": "Maharashtra",
        "company_type": "Public Limited",
        "industry": "Petrochemicals & Refining",
        "revenue": 8_97_128_00_00_000,
        "ebitda": 1_54_000_00_00_000,
        "current_ratio": 1.42,
        "debt_to_equity": 0.37,
        "paid_up_capital": 6_766_00_00_000,
        "risk_score": 22,
        "risk_flags": [],
    },
    "L17110MH": {
        "name": "Tata Consultancy Services Limited",
        "cin": "L17110MH1995PLC084781",
        "status": "ACTIVE",
        "incorporation_date": "1995-01-19",
        "registered_state": "Maharashtra",
        "company_type": "Public Limited",
        "industry": "IT Services",
        "revenue": 2_28_323_00_00_000,
        "ebitda": 53_000_00_00_000,
        "current_ratio": 2.81,
        "debt_to_equity": 0.04,
        "paid_up_capital": 366_00_00_000,
        "risk_score": 12,
        "risk_flags": [],
    },
    "L36992GJ": {
        "name": "Adani Ports and Special Economic Zone Limited",
        "cin": "L36992GJ1998PLC034182",
        "status": "ACTIVE",
        "incorporation_date": "1998-05-26",
        "registered_state": "Gujarat",
        "company_type": "Public Limited",
        "industry": "Ports & Logistics",
        "revenue": 22_923_00_00_000,
        "ebitda": 12_000_00_00_000,
        "current_ratio": 0.87,
        "debt_to_equity": 1.73,
        "paid_up_capital": 2_161_00_00_000,
        "risk_score": 58,
        "risk_flags": ["HIGH_DEBT", "REGULATORY_SCRUTINY"],
    },
}

_DEFAULT_DEMO: Dict[str, Any] = {
    "name": "Demo Entity",
    "status": "ACTIVE",
    "risk_score": 45,
    "risk_flags": ["DEMO_DATA"],
    "revenue": None,
    "ebitda": None,
    "current_ratio": None,
    "debt_to_equity": None,
    "paid_up_capital": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk_band(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _metric_color(label: str, value: Any) -> str:
    """Return a colour token based on business rules."""
    if value is None:
        return "gray"
    if label == "Current Ratio":
        return "red" if value < 1.0 else ("green" if value >= 1.5 else "amber")
    if label == "Debt to Equity":
        return "red" if value > 5 else ("amber" if value > 2 else "green")
    return "gray"


def _format_inr(value: Optional[float]) -> Optional[str]:
    """Format a value in paise/raw INR to a readable crore string."""
    if value is None:
        return None
    crore = value / 1e7
    if crore >= 1_00_000:
        return f"₹{crore / 1_00_000:.2f} Lakh Cr"
    if crore >= 1_000:
        return f"₹{crore / 1_000:.2f} Thousand Cr"
    return f"₹{crore:.2f} Cr"


def _build_company_metrics(props: Dict) -> List[Dict]:
    metrics = []

    # Look for FY-prefixed financial properties first (e.g. FY2024_revenue), then plain keys
    def _find_fy(base: str) -> Optional[float]:
        for year in (2024, 2023, 2022, 2025):
            v = props.get(f"FY{year}_{base}") or props.get(f"fy{year}_{base}")
            if v is not None:
                return float(v)
        nested = props.get("financials")
        if isinstance(nested, dict):
            return nested.get(base)
        return props.get(base)

    revenue = _find_fy("revenue")
    ebitda = _find_fy("ebitda")
    current_ratio = props.get("current_ratio") or props.get("currentRatio")
    debt_to_equity = props.get("debt_to_equity") or props.get("debtToEquity")
    paid_up_capital = props.get("paid_up_capital") or props.get("paidUpCapital")
    status = props.get("status", "UNKNOWN")

    metrics.append({
        "label": "Revenue",
        "value": _format_inr(revenue),
        "trend": "up",
        "color": "green" if revenue else "gray",
        "sparkline": None,
        "source": "MCA Financials",
    })
    metrics.append({
        "label": "EBITDA",
        "value": _format_inr(ebitda),
        "trend": "stable",
        "color": "green" if ebitda else "gray",
        "sparkline": None,
        "source": "MCA Financials",
    })
    metrics.append({
        "label": "Current Ratio",
        "value": current_ratio,
        "trend": None,
        "color": _metric_color("Current Ratio", current_ratio),
        "sparkline": None,
        "source": "MCA Financials",
    })
    metrics.append({
        "label": "Debt to Equity",
        "value": debt_to_equity,
        "trend": None,
        "color": _metric_color("Debt to Equity", debt_to_equity),
        "sparkline": None,
        "source": "MCA Financials",
    })
    metrics.append({
        "label": "Paid Up Capital",
        "value": _format_inr(paid_up_capital),
        "trend": None,
        "color": "gray",
        "sparkline": None,
        "source": "MCA Registry",
    })
    metrics.append({
        "label": "Status",
        "value": status,
        "trend": None,
        "color": "green" if status == "ACTIVE" else ("red" if status in ("STRUCK_OFF", "DISSOLVED") else "amber"),
        "sparkline": None,
        "source": "MCA Registry",
    })
    return metrics


def _build_director_metrics(props: Dict) -> List[Dict]:
    return [
        {
            "label": "Active Appointments",
            "value": props.get("currentDirectorships", props.get("active_appointments", props.get("appointments_count"))),
            "trend": None,
            "color": "gray",
            "sparkline": None,
            "source": "MCA DIN",
        },
        {
            "label": "Total Companies",
            "value": props.get("historicalDirectorships", props.get("total_companies", props.get("companies_count"))),
            "trend": None,
            "color": "gray",
            "sparkline": None,
            "source": "MCA DIN",
        },
        {
            "label": "DIN Status",
            "value": props.get("din_status", props.get("status", "ACTIVE")),
            "trend": None,
            "color": "green" if props.get("din_status", "ACTIVE") == "ACTIVE" else "red",
            "sparkline": None,
            "source": "MCA DIN",
        },
    ]


def _build_project_metrics(props: Dict) -> List[Dict]:
    return [
        {
            "label": "Budget",
            "value": _format_inr(props.get("budget")),
            "trend": None,
            "color": "gray",
            "sparkline": None,
            "source": "RERA",
        },
        {
            "label": "Completion %",
            "value": props.get("completion_percentage"),
            "trend": "up" if (props.get("completion_percentage") or 0) > 50 else "down",
            "color": "green" if (props.get("completion_percentage") or 0) > 80 else "amber",
            "sparkline": None,
            "source": "RERA",
        },
        {
            "label": "Delay Days",
            "value": props.get("delay_days"),
            "trend": "down",
            "color": "red" if (props.get("delay_days") or 0) > 180 else "amber",
            "sparkline": None,
            "source": "RERA",
        },
        {
            "label": "Status",
            "value": props.get("status", "UNKNOWN"),
            "trend": None,
            "color": "green" if props.get("status") == "COMPLETED" else "amber",
            "sparkline": None,
            "source": "RERA",
        },
    ]


def _get_demo_data(entity_type: str, entity_id: str) -> Dict:
    """Return demo company properties keyed by CIN prefix."""
    if entity_type == "company":
        for prefix, data in _DEMO_COMPANIES.items():
            if entity_id.startswith(prefix) or entity_id == data.get("cin"):
                return data
        return _DEFAULT_DEMO.copy()
    return _DEFAULT_DEMO.copy()


# ---------------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------------

async def build_entity_profile(
    clients: LayerClients,
    entity_type: str,
    entity_id: str,
    client_id: str = "PLATFORM_GLOBAL",
) -> Dict:
    """
    Fetch all entity data from Layers 3, 4, and 5 concurrently and assemble
    an EntityProfileResponse dict.

    Falls back gracefully when any upstream layer is unavailable.
    """
    # Concurrent fetch from all layers — every L3/L4 call carries the caller's client_id
    (
        entity_data,
        risk_data,
        alerts,
        timeline,
        l4_network,
        influence,
        trends,
        benchmark,
    ) = await asyncio.gather(
        clients.get_entity(entity_type, entity_id, client_id=client_id),
        clients.get_risk_score(entity_type, entity_id, client_id=client_id),
        clients.get_alerts(entity_id=entity_id, limit=10, client_id=client_id),
        clients.get_timeline(entity_type, entity_id, client_id=client_id),
        clients.get_l4_network(entity_type, entity_id, client_id=client_id),
        clients.get_influence_scores(entity_type, entity_id, client_id=client_id),
        clients.get_trends(entity_id, entity_type),
        clients.get_benchmark(entity_id, entity_type),
        return_exceptions=False,
    )

    # ML predictions (only relevant for companies/projects)
    cirp_pred: Optional[Dict] = None
    project_pred: Optional[Dict] = None
    if entity_type == "company":
        cirp_pred = await clients.get_cirp_prediction(entity_id)
    elif entity_type == "project":
        project_pred = await clients.get_project_prediction(entity_id)

    # -----------------------------------------------------------------------
    # Assemble properties — fall back to demo data if L3 is unavailable
    # -----------------------------------------------------------------------
    using_demo = entity_data is None
    if using_demo:
        logger.info(
            "Layer 3 unavailable for %s/%s — using demo data.", entity_type, entity_id
        )
        demo = _get_demo_data(entity_type, entity_id)
        props = demo
        entity_name: str = demo.get("name", entity_id)
    else:
        props = entity_data.get("properties", entity_data)
        entity_name = (
            props.get("name")
            or props.get("company_name")
            or props.get("director_name")
            or props.get("project_name")
            or entity_id
        )

    # -----------------------------------------------------------------------
    # Risk score
    # -----------------------------------------------------------------------
    raw_risk_score: int = 0
    risk_flags: List[str] = []
    if risk_data:
        raw_risk_score = int(risk_data.get("risk_score", 0))
        risk_flags = risk_data.get("risk_flags", [])
    elif using_demo:
        raw_risk_score = int(props.get("risk_score", 0))
        risk_flags = props.get("risk_flags", [])

    risk_band = _risk_band(raw_risk_score)

    # -----------------------------------------------------------------------
    # Metrics (type-specific)
    # -----------------------------------------------------------------------
    if entity_type == "company":
        metrics = _build_company_metrics(props)
    elif entity_type == "director":
        metrics = _build_director_metrics(props)
    elif entity_type == "project":
        metrics = _build_project_metrics(props)
    else:
        metrics = []

    # -----------------------------------------------------------------------
    # Generate narrative (Layer 5 LLM call with assembled context)
    # -----------------------------------------------------------------------
    narrative_context = {
        "entity_name": entity_name,
        "risk_score": raw_risk_score,
        "risk_flags": risk_flags,
        "status": props.get("status", "UNKNOWN"),
        "industry": props.get("industry", ""),
        "registered_state": props.get("registeredState") or props.get("registered_state", ""),
        "company_type": props.get("companyType") or props.get("company_type", ""),
        "incorporation_date": props.get("incorporationDate") or props.get("incorporation_date", ""),
        "current_directorships": props.get("currentDirectorships"),
        "historical_directorships": props.get("historicalDirectorships"),
        "disqualification_status": props.get("disqualificationStatus", "None"),
        "is_offshore": props.get("isOffshore", False),
        "delay_days": props.get("delay_days") or props.get("delayDays"),
        "completion_pct": props.get("completion_percentage") or props.get("completionPercentage"),
        "promoter_cin": props.get("promoterCin", ""),
    }
    narrative: Optional[str] = await clients.generate_narrative(
        entity_type, entity_id, narrative_context
    )
    if not narrative:
        flag_str = ", ".join(risk_flags) if risk_flags else "no notable flags"
        if entity_type == "company":
            state = props.get("registeredState") or props.get("registered_state", "")
            industry = props.get("industry", "")
            status = props.get("status", "UNKNOWN")
            inc_date = props.get("incorporationDate") or props.get("incorporation_date", "")
            state_str = f" registered in {state}" if state else ""
            industry_str = f" operating in {industry}" if industry else ""
            inc_str = f", incorporated {inc_date}" if inc_date else ""
            cirp_note = " The company is currently under CIRP proceedings." if "CIRP_ACTIVE" in risk_flags else ""
            narrative = (
                f"{entity_name} is a {status.lower()} Indian company{state_str}{industry_str}{inc_str}. "
                f"Risk score: {raw_risk_score}/100 ({risk_band}) with flags: {flag_str}.{cirp_note} "
                f"Connect Layer 5 for LLM-enriched due diligence analysis."
            )
        elif entity_type == "director":
            current_dirs = props.get("currentDirectorships")
            hist_dirs = props.get("historicalDirectorships")
            disq = props.get("disqualificationStatus", "None")
            offshore = props.get("isOffshore", False)
            dirs_str = f" Currently holds {current_dirs} active directorship(s)" if current_dirs else ""
            hist_str = f" with {hist_dirs} historical appointments" if hist_dirs else ""
            disq_str = " Director is disqualified under Section 164(2) of the Companies Act." if disq == "Disqualified" else ""
            offshore_str = " Director has non-Indian nationality." if offshore else ""
            narrative = (
                f"{entity_name} is an Indian corporate director (DIN: {entity_id}).{dirs_str}{hist_str}. "
                f"Risk score: {raw_risk_score}/100 ({risk_band}) with flags: {flag_str}.{disq_str}{offshore_str} "
                f"Connect Layer 5 for LLM-enriched director intelligence."
            )
        elif entity_type == "project":
            proj_status = props.get("status", "UNKNOWN")
            delay = props.get("delay_days") or props.get("delayDays")
            comp_pct = props.get("completion_percentage") or props.get("completionPercentage")
            delay_str = f" Delayed by {delay} days." if delay and delay > 0 else ""
            comp_str = f" Completion: {comp_pct}%." if comp_pct is not None else ""
            narrative = (
                f"{entity_name} is a RERA-registered project with status '{proj_status}'.{comp_str}{delay_str} "
                f"Risk score: {raw_risk_score}/100 ({risk_band}) with flags: {flag_str}. "
                f"Connect Layer 5 for LLM-enriched project intelligence."
            )
        else:
            narrative = (
                f"{entity_name} ({entity_type}) — risk score {raw_risk_score}/100 ({risk_band}), flags: {flag_str}. "
                f"Connect Layer 5 for LLM-enriched analysis."
            )

    # -----------------------------------------------------------------------
    # ML Predictions
    # -----------------------------------------------------------------------
    cirp_probability: Optional[float] = None
    project_completion_probability: Optional[float] = None
    ml_confidence: Optional[float] = None

    if cirp_pred:
        cirp_probability = cirp_pred.get("cirp_probability") or cirp_pred.get("probability")
        ml_confidence = cirp_pred.get("confidence")
    if project_pred:
        project_completion_probability = (
            project_pred.get("completion_probability") or project_pred.get("probability")
        )
        ml_confidence = ml_confidence or project_pred.get("confidence")

    # -----------------------------------------------------------------------
    # Graph / influence data from Layer 4
    # -----------------------------------------------------------------------
    influence_score: Optional[float] = None
    cluster_info: Optional[Dict] = None

    if influence:
        influence_score = influence.get("influence_score") or influence.get("betweenness_centrality")
        cluster_info = influence.get("cluster_info") or influence.get("cluster")

    if l4_network and cluster_info is None:
        cluster_info = l4_network.get("cluster_info")

    # -----------------------------------------------------------------------
    # Assemble final response
    # -----------------------------------------------------------------------
    return {
        "entityType": entity_type,
        "entityId": entity_id,
        "name": entity_name,
        "riskScore": raw_risk_score,
        "riskBand": risk_band,
        "riskFlags": risk_flags,
        "properties": props,
        "intelligenceSummary": narrative,
        "metrics": metrics,
        "activeAlerts": alerts or [],
        "recentEvents": timeline or [],
        "mlPredictions": {
            "cirpProbability": cirp_probability,
            "projectCompletionProbability": project_completion_probability,
            "confidence": ml_confidence,
        },
        "trends": trends.get("trends") if isinstance(trends, dict) else trends,
        "benchmark": benchmark,
        "influenceScore": influence_score,
        "clusterInfo": cluster_info,
        "dataFreshness": {
            "source": "demo" if using_demo else "live",
            "lastSynced": datetime.now(timezone.utc).isoformat(),
        },
    }
