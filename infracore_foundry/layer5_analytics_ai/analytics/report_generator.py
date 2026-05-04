"""
Structured report assembler — combines data, risk scores, benchmarks,
trend analysis, and LLM narrative sections into a complete deliverable.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

from core.config import settings
from core.database import get_pool
from analytics.benchmarking import get_benchmarks
from analytics.trend_detector import get_trend
from models.serving import model_server, MODEL_CIRP_PRECURSOR
from llm.workflows.summarization import summarize_company, explain_cirp_risk

logger = logging.getLogger(__name__)


async def generate_due_diligence_report(
    cin: str,
    actor_id: str = "system",
    actor_role: str = "Analyst",
    agent_run_id: str | None = None,
) -> dict:
    """
    Assembles a full Corporate Due Diligence Report for the given CIN.
    Returns a structured dict. Persists to l5_reports.
    """
    report_id = str(uuid.uuid4())
    sections: dict = {}

    # Section 1 — Entity profile from L3
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.layer3_api_url}/api/v1/objects/company/{cin}")
            company = resp.json() if resp.status_code == 200 else {}
            sections["entity_profile"] = company
    except Exception as exc:
        logger.warning("L3 company fetch failed for %s: %s", cin, exc)
        sections["entity_profile"] = {"error": str(exc)}

    props = sections["entity_profile"].get("properties", {})
    company_name = props.get("name", cin)
    risk_score = int(props.get("riskScore", 0))
    risk_flags = props.get("riskFlags", [])

    # Section 2 — Network from L4
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.layer4_api_url}/api/v1/network/{cin}",
                params={"depth": 2},
            )
            sections["network"] = resp.json() if resp.status_code == 200 else {}
    except Exception as exc:
        sections["network"] = {"error": str(exc)}

    # Section 3 — CIRP ML prediction
    try:
        pred = await model_server.predict(MODEL_CIRP_PRECURSOR, "Company", cin, persist=True)
        sections["cirp_prediction"] = pred.to_dict()
    except Exception as exc:
        sections["cirp_prediction"] = {"error": str(exc), "prediction_value": None}

    cirp_prob = sections["cirp_prediction"].get("prediction_value") or 0.0
    shap_vals = sections["cirp_prediction"].get("shap_values")

    # Section 4 — CIRP risk explanation (LLM)
    try:
        sections["cirp_explanation"] = await explain_cirp_risk(
            company_name=company_name,
            probability=cirp_prob,
            shap_values=shap_vals,
            actor_id=actor_id,
            actor_role=actor_role,
        )
    except Exception as exc:
        sections["cirp_explanation"] = f"Explanation unavailable: {exc}"

    # Section 5 — Benchmark comparison
    sections["benchmarks"] = await get_benchmarks("Company", cin)

    benchmark_summary = (
        f"{len(sections['benchmarks'])} metrics benchmarked against sector peers"
        if sections["benchmarks"] else "No benchmark data available"
    )

    # Section 6 — Trend analysis (current_ratio, risk score)
    sections["trends"] = {}
    for metric in ["current_ratio", "layer3_risk_score", "regulatory_action_count_12m"]:
        trend = await get_trend("Company", cin, metric)
        if trend:
            sections["trends"][metric] = trend

    # Section 7 — Executive summary (LLM)
    try:
        financials = (
            f"Current ratio: {props.get('currentRatio', 'N/A')}, "
            f"D/E: {props.get('debtEquityRatio', 'N/A')}"
        )
        sections["executive_summary"] = await summarize_company(
            cin=cin,
            actor_id=actor_id,
            actor_role=actor_role,
            cirp_probability=cirp_prob,
            risk_score=risk_score,
            risk_flags=risk_flags,
            financials=financials,
            benchmark_summary=benchmark_summary,
        )
    except Exception as exc:
        sections["executive_summary"] = f"Summary unavailable: {exc}"

    report = {
        "report_id": report_id,
        "report_type": "corporate_due_diligence",
        "entity_type": "Company",
        "entity_id": cin,
        "title": f"Corporate Due Diligence Report — {company_name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": actor_id,
        "sections": sections,
    }

    # Persist report
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO l5_reports
                    (report_id, report_type, entity_type, entity_id, title,
                     content_json, generated_by, agent_run_id)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                """,
                report_id, "corporate_due_diligence", "Company", cin,
                report["title"],
                json.dumps(report, default=str),
                actor_id,
                uuid.UUID(agent_run_id) if agent_run_id else None,
            )
    except Exception as exc:
        logger.warning("Report persist failed: %s", exc)

    return report
