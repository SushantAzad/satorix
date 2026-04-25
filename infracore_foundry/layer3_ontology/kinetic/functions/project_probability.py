from dataclasses import dataclass
from typing import Any
import logging
from core.database import AsyncSessionLocal
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)


@dataclass
class ProjectCompletionForecast:
    probability: float
    confidence: str
    risk_factors: list[str]
    score_breakdown: dict[str, int]


async def predictProjectCompletionProbability(project_id: str) -> ProjectCompletionForecast:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT properties FROM ontology_objects WHERE object_type = 'project' AND primary_key = :pk"),
            {"pk": project_id},
        )
        row = result.first()
        if not row:
            return ProjectCompletionForecast(probability=0.5, confidence="LOW", risk_factors=["Project not found"], score_breakdown={})

        props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")

    score = 100
    risk_factors: list[str] = []
    breakdown: dict[str, int] = {}

    delay_months = int(props.get("delayMonths", 0) or 0)
    delay_deduction = min(delay_months * 5, 40)
    score -= delay_deduction
    if delay_months > 0:
        breakdown["delay_penalty"] = -delay_deduction
        risk_factors.append(f"{delay_months} months delay")

    land_status = str(props.get("landAcquisitionStatus", "")).lower()
    if "incomplete" in land_status or "pending" in land_status:
        score -= 15
        breakdown["land_acquisition"] = -15
        risk_factors.append("Land acquisition incomplete")

    cost_overrun = float(props.get("costOverrunPercent", 0) or 0)
    if cost_overrun > 20:
        score -= 20
        breakdown["cost_overrun"] = -20
        risk_factors.append(f"{cost_overrun:.0f}% cost overrun")

    owner_risk = 0
    try:
        from core.neo4j_client import neo4j_client
        owner_results = await neo4j_client.run_query(
            "MATCH (c:Company)-[:OWNS_PROJECT]->(p:Project {projectId: $pid}) RETURN c.riskScore AS rs",
            {"pid": project_id},
        )
        if owner_results:
            owner_risk = owner_results[0].get("rs", 0) or 0
    except Exception:
        pass

    if owner_risk > 70:
        score -= 25
        breakdown["owner_risk"] = -25
        risk_factors.append("High-risk owner company")

    probability = max(0.0, min(1.0, score / 100))
    confidence = "HIGH" if len(risk_factors) < 2 else ("MEDIUM" if len(risk_factors) < 4 else "LOW")

    return ProjectCompletionForecast(
        probability=round(probability, 3),
        confidence=confidence,
        risk_factors=risk_factors,
        score_breakdown=breakdown,
    )
