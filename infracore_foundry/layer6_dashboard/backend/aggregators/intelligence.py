"""
IntelligenceAggregator — assembles the data for the Intelligence dashboard page.

Combines:
  - L5 CIRP risk prediction + features
  - L5 trend analysis
  - L5 correlation signals
  - L5 scenario analysis
  - L3 risk score and anomaly alerts
  - L4 network influence scores

All calls are made in parallel and failures are handled gracefully.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.layer_clients import layer_clients

logger = logging.getLogger(__name__)


async def get_intelligence_dashboard(
    cin: str, client_id: str = "PLATFORM_GLOBAL"
) -> Dict[str, Any]:
    """
    Build the full intelligence payload for a company.
    Called by GET /api/v1/intelligence/{cin}.
    """
    (
        prediction,
        features,
        trends,
        benchmark,
        correlations,
        scenarios,
        risk_score,
        network,
    ) = await asyncio.gather(
        layer_clients.get_cirp_prediction(cin),
        layer_clients.get_entity_features(cin),
        layer_clients.get_trends(cin, "company"),
        layer_clients.get_benchmark(cin, "company"),
        layer_clients.get_correlations(cin),
        layer_clients.get_scenarios(cin),
        layer_clients.get_risk_score("company", cin, client_id),
        layer_clients.get_influence_scores("company", cin, client_id),
        return_exceptions=True,
    )

    def _safe(val):
        return val if not isinstance(val, Exception) else None

    prediction = _safe(prediction)
    features = _safe(features)
    trends = _safe(trends)
    benchmark = _safe(benchmark)
    correlations = _safe(correlations)
    scenarios = _safe(scenarios)
    risk_score = _safe(risk_score)
    network_influence = _safe(network)

    # Build risk signal summary from features
    risk_signals: List[Dict] = []
    if features and isinstance(features, dict):
        signal_map = {
            "is_under_cirp":            ("CIRP Active", "critical"),
            "regulatory_action_ongoing": ("Ongoing Regulatory Actions", "high"),
            "director_disqualified_count": ("Disqualified Directors", "high"),
            "director_offshore_ratio":   ("Offshore Director Exposure", "medium"),
            "days_since_last_filing":    ("Filing Compliance Gap", "medium"),
            "revenue_cagr_3y":           ("Revenue Trend (3Y CAGR %)", "info"),
            "ebitda_margin_latest":      ("EBITDA Margin (%)", "info"),
            "debt_equity_ratio":         ("Debt/Equity Ratio", "info"),
            "current_ratio":             ("Current Ratio", "info"),
        }
        for feat_name, (label, severity) in signal_map.items():
            val = features.get(feat_name)
            if val is not None:
                risk_signals.append({
                    "name": label,
                    "feature": feat_name,
                    "value": val,
                    "severity": severity,
                })

    return {
        "cin": cin,
        "prediction": prediction or {},
        "features": features or {},
        "risk_signals": risk_signals,
        "trends": trends or {},
        "benchmark": benchmark or {},
        "correlations": correlations or {},
        "scenarios": scenarios or {},
        "risk_score": risk_score or {},
        "network_influence": network_influence or {},
    }


async def ask_intelligence_question(
    question: str, cin: Optional[str] = None
) -> Dict[str, Any]:
    """
    Route an open-ended question to the Layer 5 GraphIntelligenceAgent.
    Called by POST /api/v1/intelligence/ask.
    """
    result = await layer_clients.ask_intelligence_question(question, cin)
    if result is None:
        return {
            "answer": "[Intelligence engine unavailable. Please try again or contact support.]",
            "status": "error",
        }
    return result
