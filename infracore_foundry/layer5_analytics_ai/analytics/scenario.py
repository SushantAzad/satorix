"""
Scenario simulator — sandbox for projecting consequences of hypothetical changes.
Does NOT modify the actual ontology. Runs in-memory with projected values.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from core.database import get_pool
from feature_store.feature_store import get_latest_features
from feature_store.feature_registry import get_feature_defaults

logger = logging.getLogger(__name__)


class ScenarioSimulator:

    async def simulate(
        self,
        base_entity_type: str,
        base_entity_id: str,
        modifications: dict[str, Any],
        scenario_name: str = "",
        created_by: str = "system",
    ) -> dict:
        """
        Apply `modifications` to the entity's current feature vector and
        recompute downstream metrics. Returns projected outcomes.
        Does not touch any live data.
        """
        # Load current features
        current_features = await get_latest_features(base_entity_type, base_entity_id)
        if current_features is None:
            current_features = get_feature_defaults(base_entity_type)

        # Apply modifications to a copy
        projected_features = dict(current_features)
        for key, val in modifications.items():
            projected_features[key] = val

        outcomes = await self._project_outcomes(
            base_entity_type, base_entity_id, current_features, projected_features
        )

        # Persist scenario
        pool = get_pool()
        scenario_id = str(uuid.uuid4())
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO l5_scenarios
                        (scenario_id, scenario_name, base_entity_type, base_entity_id,
                         modifications, projected_outcomes, created_by)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                    """,
                    scenario_id, scenario_name or f"Scenario {scenario_id[:8]}",
                    base_entity_type, base_entity_id,
                    json.dumps(modifications, default=str),
                    json.dumps(outcomes, default=str),
                    created_by,
                )
        except Exception as exc:
            logger.warning("Scenario persist failed: %s", exc)

        return {
            "scenario_id": scenario_id,
            "base_entity_id": base_entity_id,
            "modifications": modifications,
            "current_state": self._summarize_features(current_features),
            "projected_state": self._summarize_features(projected_features),
            "projected_outcomes": outcomes,
        }

    async def _project_outcomes(
        self,
        entity_type: str,
        entity_id: str,
        current: dict,
        projected: dict,
    ) -> dict:
        """Compute how key metrics change between current and projected feature sets."""
        outcomes: dict = {}

        # CIRP risk delta
        current_cirp = self._heuristic_cirp_score(current)
        projected_cirp = self._heuristic_cirp_score(projected)
        outcomes["cirp_risk_score"] = {
            "current": round(current_cirp, 3),
            "projected": round(projected_cirp, 3),
            "delta": round(projected_cirp - current_cirp, 3),
        }

        # Risk score delta (L3 rule proxy)
        current_risk = float(current.get("layer3_risk_score", 0))
        # Apply simple deltas based on what changed
        risk_delta = 0.0
        if projected.get("is_under_cirp", 0) > current.get("is_under_cirp", 0):
            risk_delta += 30
        if projected.get("regulatory_action_ongoing", 0) > current.get("regulatory_action_ongoing", 0):
            risk_delta += (projected["regulatory_action_ongoing"] - current["regulatory_action_ongoing"]) * 10
        if projected.get("director_offshore_ratio", 0) > current.get("director_offshore_ratio", 0):
            risk_delta += 5
        outcomes["risk_score"] = {
            "current": round(current_risk, 1),
            "projected": round(min(100.0, current_risk + risk_delta), 1),
            "delta": round(risk_delta, 1),
        }

        # Changed features summary
        outcomes["changed_features"] = {
            k: {"from": current.get(k), "to": v}
            for k, v in projected.items()
            if current.get(k) != v
        }

        return outcomes

    def _heuristic_cirp_score(self, feats: dict) -> float:
        score = 0.0
        if feats.get("is_under_cirp", 0) >= 1:
            return 1.0
        score += min(feats.get("l4_precursor_score", 0) / 100.0, 0.5)
        score += min(feats.get("regulatory_action_ongoing", 0) * 0.1, 0.3)
        if feats.get("current_ratio") is not None and feats["current_ratio"] < 0.5:
            score += 0.2
        return min(score, 1.0)

    def _summarize_features(self, feats: dict) -> dict:
        key_metrics = [
            "layer3_risk_score", "l4_precursor_score", "current_ratio",
            "debt_equity_ratio", "is_under_cirp", "regulatory_action_ongoing",
            "director_offshore_ratio", "avg_project_delay_months",
        ]
        return {k: feats.get(k) for k in key_metrics if feats.get(k) is not None}


scenario_simulator = ScenarioSimulator()
