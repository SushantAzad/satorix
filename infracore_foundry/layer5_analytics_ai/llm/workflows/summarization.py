"""
Entity and group summarization workflows.
"""
import json
import logging

from llm.orchestrator import llm_orchestrator
from llm.context_builder import build_company_context, format_context_for_prompt

logger = logging.getLogger(__name__)


async def summarize_company(
    cin: str,
    actor_id: str = "system",
    actor_role: str = "Analyst",
    cirp_probability: float = 0.0,
    risk_score: int = 0,
    risk_flags: list[str] | None = None,
    financials: str = "N/A",
    benchmark_summary: str = "N/A",
) -> str:
    ctx = await build_company_context(cin, actor_role=actor_role)
    company_props = ctx.get("company", {})
    company_name = company_props.get("name", cin)
    status = company_props.get("status", "Unknown")

    high_risk = [n for n in ctx.get("high_risk_neighbours", [])]
    network_summary = f"{ctx.get('network_node_count', 0)} nodes, {len(high_risk)} high-risk neighbours"

    return await llm_orchestrator.run(
        prompt_key="due_diligence_summary_v1",
        format_kwargs={
            "company_name": company_name,
            "cin": cin,
            "status": status,
            "risk_score": risk_score,
            "risk_flags": ", ".join(risk_flags or []) or "none",
            "cirp_probability": cirp_probability,
            "financials": financials,
            "network_summary": network_summary,
            "benchmark_summary": benchmark_summary,
        },
        actor_id=actor_id,
        actor_role=actor_role,
        objects_accessed=ctx.get("_objects_accessed", [f"Company:{cin}"]),
        output_disposition="returned",
        max_tokens=400,
        workflow_type="summarization",
    )


async def generate_entity_intelligence(
    entity_type: str,
    entity_id: str,
    context: dict,
    actor_id: str = "system",
    actor_role: str = "Analyst",
) -> str:
    """
    Generate a contextual intelligence summary for any entity type using Ollama.
    Called by Layer 6 via POST /api/v1/llm/entity-intelligence.
    Uses the entity_intelligence_v1 prompt which is tuned for Indian corporate context.
    """
    # Extract key properties from context for the prompt
    entity_name = context.get("entity_name") or entity_id
    risk_score = context.get("risk_score", 0)
    risk_band = context.get("risk_band", "UNKNOWN")
    risk_flags = context.get("risk_flags", [])
    status = context.get("status", "UNKNOWN")

    # Build type-specific key properties string
    key_props: dict = {}
    if entity_type == "company":
        for k in ("industry", "registered_state", "incorporation_date", "company_type",
                  "FY2024_revenue", "FY2024_ebitda", "current_ratio", "debt_to_equity"):
            v = context.get(k)
            if v is not None:
                key_props[k] = v
        # Include network data if available
        if context.get("promoter_cin"):
            key_props["promoter_cin"] = context["promoter_cin"]
    elif entity_type == "director":
        for k in ("currentDirectorships", "historicalDirectorships", "disqualificationStatus",
                  "isOffshore", "nationality", "current_directorships", "historical_directorships",
                  "disqualification_status", "is_offshore"):
            v = context.get(k)
            if v is not None:
                key_props[k] = v
    elif entity_type == "project":
        for k in ("completion_percentage", "delay_days", "promoter_cin", "reraState",
                  "sanctionedUnits", "soldUnits", "expectedCompletion", "isDelayed"):
            v = context.get(k)
            if v is not None:
                key_props[k] = v

    # For companies: enrich context from Layer 3 if not already provided
    if entity_type == "company" and not key_props.get("industry"):
        try:
            ctx = await build_company_context(entity_id, actor_role=actor_role)
            company = ctx.get("company", {})
            if company:
                key_props.update({k: v for k, v in company.items()
                                   if k in ("industry", "registeredState", "status", "riskScore",
                                            "incorporationDate", "companyType") and v is not None})
                if ctx.get("network_node_count"):
                    key_props["network_connections"] = ctx["network_node_count"]
                if ctx.get("high_risk_neighbours"):
                    key_props["high_risk_neighbours"] = len(ctx["high_risk_neighbours"])
        except Exception as exc:
            logger.debug("Context enrichment failed for %s: %s", entity_id, exc)

    key_properties_str = json.dumps(key_props, default=str) if key_props else "No additional properties available"
    risk_flags_str = ", ".join(str(f) for f in risk_flags) if risk_flags else "none"

    return await llm_orchestrator.run(
        prompt_key="entity_intelligence_v1",
        format_kwargs={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "risk_score": risk_score,
            "risk_band": risk_band,
            "risk_flags": risk_flags_str,
            "status": status,
            "key_properties": key_properties_str,
        },
        actor_id=actor_id,
        actor_role=actor_role,
        objects_accessed=[f"{entity_type.capitalize()}:{entity_id}"],
        output_disposition="returned",
        max_tokens=350,
        use_cache=True,
        workflow_type="entity_intelligence",
    )


async def explain_cirp_risk(
    company_name: str,
    probability: float,
    shap_values: dict | None,
    actor_id: str = "system",
    actor_role: str = "Analyst",
) -> str:
    if shap_values:
        sorted_shap = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        shap_summary = "\n".join(
            f"  • {feat}: {'+' if val > 0 else ''}{val:.3f}" for feat, val in sorted_shap
        )
    else:
        shap_summary = "  • Feature contributions not available (heuristic model)"

    return await llm_orchestrator.run(
        prompt_key="cirp_risk_explanation_v1",
        format_kwargs={
            "company_name": company_name,
            "probability": probability,
            "shap_summary": shap_summary,
        },
        actor_id=actor_id,
        actor_role=actor_role,
        output_disposition="returned",
        max_tokens=300,
        workflow_type="cirp_explanation",
    )
