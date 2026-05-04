"""
Entity and group summarization workflows.
"""
from llm.orchestrator import llm_orchestrator
from llm.context_builder import build_company_context, format_context_for_prompt


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
