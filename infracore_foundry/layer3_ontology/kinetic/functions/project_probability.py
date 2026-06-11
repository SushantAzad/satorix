"""
Project completion probability — heuristic v0.
Produces a probability [0, 1] from rule-based scoring.

Layer 5 upgrade path: this function will be replaced by an XGBoost classifier trained
on historical project completion data (GeM portal, NHAI concession outcomes, NCLT filings).
The feature vector defined here is intentionally designed to match the planned L5 training schema.

Risk factors scored:
  - Schedule delay (months)
  - Land acquisition status
  - Cost overrun percentage
  - Owner company risk score
  - Active regulatory actions count
  - CIRP / insolvency proceedings (critical)
  - Project status
"""
from dataclasses import dataclass, field
from typing import Any
import logging

from core.database import AsyncSessionLocal
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

FEATURE_SCHEMA_VERSION = "v0.3"  # Increment when features change; L5 must match


@dataclass
class ProjectCompletionForecast:
    probability: float
    confidence: str
    risk_factors: list[str]
    score_breakdown: dict[str, int]
    feature_schema_version: str = FEATURE_SCHEMA_VERSION


async def predictProjectCompletionProbability(project_id: str) -> ProjectCompletionForecast:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT properties FROM ontology_objects WHERE object_type = 'project' AND primary_key = :pk"),
            {"pk": project_id},
        )
        row = result.first()
        if not row:
            return ProjectCompletionForecast(
                probability=0.5,
                confidence="LOW",
                risk_factors=["Project not found in ontology"],
                score_breakdown={},
            )
        props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")

    score = 100
    risk_factors: list[str] = []
    breakdown: dict[str, int] = {}

    # --- Feature 1: Schedule delay ---
    delay_months = int(props.get("delayMonths", 0) or 0)
    if delay_months > 0:
        # Non-linear penalty: each extra month hurts more when already badly delayed
        delay_deduction = min(int(delay_months * 4 + (max(0, delay_months - 12) * 2)), 45)
        score -= delay_deduction
        breakdown["schedule_delay"] = -delay_deduction
        risk_factors.append(f"{delay_months} month schedule overrun")

    # --- Feature 2: Land acquisition ---
    land_status = str(props.get("landAcquisitionStatus", "")).lower()
    if "incomplete" in land_status or "pending" in land_status or "disputed" in land_status:
        deduction = 20 if "disputed" in land_status else 15
        score -= deduction
        breakdown["land_acquisition"] = -deduction
        risk_factors.append(f"Land acquisition {land_status}")

    # --- Feature 3: Cost overrun ---
    cost_overrun = float(props.get("costOverrunPercent", 0) or 0)
    if cost_overrun > 10:
        overrun_deduction = min(int((cost_overrun - 10) * 1.5 + 10), 30)
        score -= overrun_deduction
        breakdown["cost_overrun"] = -overrun_deduction
        risk_factors.append(f"{cost_overrun:.0f}% cost overrun")

    # --- Feature 4: Project status ---
    status = str(props.get("status", "")).lower()
    if status in ("stalled", "suspended", "terminated"):
        score -= 40
        breakdown["project_status"] = -40
        risk_factors.append(f"Project status: {status}")
    elif status == "delayed":
        score -= 10
        breakdown["project_status"] = -10

    # --- Feature 5: Owner company risk + CIRP check ---
    owner_risk = 0
    try:
        from core.neo4j_client import neo4j_client
        owner_results = await neo4j_client.run_query(
            """
            MATCH (c:Company)-[:OWNS_PROJECT]->(p:Project {projectId: $pid})
            OPTIONAL MATCH (c)-[:SUBJECT_OF]->(ip:InsolvencyProceeding {status: 'Active'})
            RETURN c.riskScore AS rs, c.name AS name, count(ip) AS cirp_count
            """,
            {"pid": project_id},
        )
        if owner_results:
            owner_risk = float(owner_results[0].get("rs") or 0)
            cirp_count = int(owner_results[0].get("cirp_count") or 0)
            if cirp_count > 0:
                score -= 50  # CIRP is near-fatal for project completion
                breakdown["owner_cirp"] = -50
                risk_factors.append(f"Owner company under CIRP proceedings")
            elif owner_risk > 70:
                deduction = min(int((owner_risk - 70) * 0.8), 25)
                score -= deduction
                breakdown["owner_risk"] = -deduction
                risk_factors.append(f"High-risk owner (score {owner_risk:.0f})")
    except Exception as _neo_exc:
        logger.debug("Neo4j owner query failed (non-fatal): %s", _neo_exc)

    # --- Feature 6: Regulatory actions against project or owner ---
    try:
        from core.neo4j_client import neo4j_client
        reg_results = await neo4j_client.run_query(
            """
            MATCH (p:Project {projectId: $pid})<-[:RELATES_TO]-(ra:RegulatoryAction {status: 'Ongoing'})
            RETURN count(ra) AS action_count
            """,
            {"pid": project_id},
        )
        if reg_results:
            action_count = int(reg_results[0].get("action_count") or 0)
            if action_count > 0:
                deduction = min(action_count * 8, 20)
                score -= deduction
                breakdown["regulatory_actions"] = -deduction
                risk_factors.append(f"{action_count} active regulatory action(s)")
    except Exception:
        pass

    # --- Normalize and calibrate ---
    score = max(0, min(100, score))
    probability = round(score / 100, 3)

    # Confidence reflects how many data points we have (risk_factors = known issues)
    if len(risk_factors) == 0:
        confidence = "MEDIUM"  # No risk signals found — but could be data gap
    elif len(risk_factors) <= 2:
        confidence = "HIGH"
    elif len(risk_factors) <= 4:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return ProjectCompletionForecast(
        probability=probability,
        confidence=confidence,
        risk_factors=risk_factors,
        score_breakdown=breakdown,
    )
