"""
PathScorer — assigns a risk score and suspicion signals to a path.
Used by the narrative generator and the UI risk-heatmap overlay.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class ScoredPath:
    node_path: list[str]
    node_types: list[str]
    hop_count: int
    path_risk: float
    signals: list[str]
    hop_details: list[dict[str, Any]]


class PathScorer:
    # Weights for individual signals
    SIGNAL_WEIGHTS = {
        "cirp_node": 30.0,
        "regulatory_action_node": 20.0,
        "disqualified_director": 25.0,
        "offshore_director": 15.0,
        "high_risk_company": 15.0,
        "shell_company_indicator": 20.0,
        "short_directorship": 10.0,
        "circular_ownership": 35.0,
    }

    def score(
        self,
        node_path: list[str],
        node_types: list[str],
        hop_details: list[dict[str, Any]],
        node_properties: dict[str, dict],  # id → props
    ) -> ScoredPath:
        signals: list[str] = []
        accumulated = 0.0

        for i, nid in enumerate(node_path):
            props = node_properties.get(nid, {})
            ntype = node_types[i] if i < len(node_types) else "unknown"

            if props.get("status") == "UnderCIRP":
                signals.append(f"{nid} is under CIRP")
                accumulated += self.SIGNAL_WEIGHTS["cirp_node"]
            if ntype == "RegulatoryAction":
                signals.append(f"Regulatory action node: {nid}")
                accumulated += self.SIGNAL_WEIGHTS["regulatory_action_node"]
            if props.get("isDisqualified"):
                signals.append(f"Disqualified director: {nid}")
                accumulated += self.SIGNAL_WEIGHTS["disqualified_director"]
            if props.get("nationality") and props["nationality"].lower() not in ("indian", "india"):
                signals.append(f"Offshore director: {nid}")
                accumulated += self.SIGNAL_WEIGHTS["offshore_director"]
            risk = props.get("riskScore", 0) or 0
            if risk >= 70:
                signals.append(f"High-risk entity: {nid} (score={risk})")
                accumulated += self.SIGNAL_WEIGHTS["high_risk_company"]

        # Circular ownership: same entity appears twice in path
        if len(node_path) != len(set(node_path)):
            signals.append("Circular path detected")
            accumulated += self.SIGNAL_WEIGHTS["circular_ownership"]

        return ScoredPath(
            node_path=node_path,
            node_types=node_types,
            hop_count=len(hop_details),
            path_risk=min(accumulated, 100.0),
            signals=signals,
            hop_details=hop_details,
        )
