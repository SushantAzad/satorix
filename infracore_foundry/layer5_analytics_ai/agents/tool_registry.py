"""
Tool registry — all tools available to Layer 5 agents.
Each tool is an async function with a documented interface.
"""
import logging
from typing import Any

import httpx

from core.config import settings
from models.serving import model_server, MODEL_CIRP_PRECURSOR, MODEL_PROJECT_COMPLETION
from analytics.report_generator import generate_due_diligence_report
from analytics.benchmarking import compute_sector_benchmarks
from llm.workflows.narrative import generate_path_narrative
from llm.workflows.summarization import summarize_company

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(name: str, description: str):
    def decorator(fn):
        TOOL_REGISTRY[name] = {"fn": fn, "description": description}
        return fn
    return decorator


@register_tool("get_company_profile", "Fetch company profile from Layer 3 ontology")
async def get_company_profile(cin: str, **_) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{settings.layer3_api_url}/api/v1/objects/company/{cin}")
        return resp.json() if resp.status_code == 200 else {"error": resp.status_code}


@register_tool("get_network", "Fetch corporate network from Layer 4 graph intelligence")
async def get_network(cin: str, depth: int = 2, **_) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.layer4_api_url}/api/v1/network/{cin}",
            params={"depth": depth},
        )
        return resp.json() if resp.status_code == 200 else {"error": resp.status_code}


@register_tool("get_risk_score", "Get current risk score from Layer 3")
async def get_risk_score(cin: str, **_) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{settings.layer3_api_url}/api/v1/intelligence/risk/{cin}")
        return resp.json() if resp.status_code == 200 else {"error": resp.status_code}


@register_tool("get_cirp_prediction", "Get ML-based CIRP probability prediction from Layer 5")
async def get_cirp_prediction(cin: str, **_) -> dict:
    pred = await model_server.predict(MODEL_CIRP_PRECURSOR, "Company", cin)
    return pred.to_dict()


@register_tool("get_project_prediction", "Get ML-based project completion probability")
async def get_project_prediction(project_id: str, **_) -> dict:
    pred = await model_server.predict(MODEL_PROJECT_COMPLETION, "Project", project_id)
    return pred.to_dict()


@register_tool("generate_narrative", "Generate plain-English explanation of a connection path")
async def _gen_narrative(
    source_id: str,
    target_id: str,
    node_path: list[str],
    node_types: list[str],
    hop_details: list[dict],
    signals: list[str],
    actor_id: str = "system",
    **_,
) -> str:
    return await generate_path_narrative(
        source_id=source_id,
        target_id=target_id,
        node_path=node_path,
        node_types=node_types,
        hop_details=hop_details,
        signals=signals,
        node_properties={},
        actor_id=actor_id,
    )


@register_tool("run_benchmark", "Compute sector benchmark percentile rankings for a company")
async def run_benchmark(cin: str, metrics: list[str] | None = None, **_) -> dict:
    if metrics is None:
        metrics = ["layer3_risk_score", "current_ratio", "debt_equity_ratio", "avg_project_delay_months"]
    return await compute_sector_benchmarks("Company", cin, metrics)


@register_tool("generate_report", "Assemble a full due diligence report")
async def _gen_report(cin: str, actor_id: str = "system", **_) -> dict:
    return await generate_due_diligence_report(cin, actor_id=actor_id)


@register_tool("create_alert", "Create an alert via Layer 3 action API")
async def create_alert(entity_id: str, alert_type: str, message: str, actor_id: str = "system", **_) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.layer3_api_url}/api/v1/actions/create-alert",
            json={"entity_id": entity_id, "alert_type": alert_type, "message": message, "actor_id": actor_id},
        )
        return resp.json() if resp.status_code in (200, 201) else {"error": resp.status_code}


@register_tool("search_documents", "Semantic search over indexed documents for a company entity")
async def search_documents(query: str, entity_ref_id: str = None, top_k: int = 4, **_) -> list[dict]:
    from rag.semantic_retriever import retrieve
    return await retrieve(query, entity_ref_id=entity_ref_id, top_k=top_k)


@register_tool("get_financial_statements", "Fetch financial statement history for a company")
async def get_financial_statements(cin: str, years: int = 3, **_) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.layer3_api_url}/api/v1/objects/financial_statement",
            params={"cin": cin, "limit": years, "period": "annual"},
        )
        return resp.json() if resp.status_code == 200 else []


@register_tool("get_entity_features", "Get computed intelligence features for a company")
async def get_entity_features(cin: str, **_) -> dict:
    from feature_store.feature_computer import feature_computer
    return await feature_computer.compute_company_features(cin)


async def call_tool(tool_name: str, params: dict) -> Any:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")
    fn = TOOL_REGISTRY[tool_name]["fn"]
    return await fn(**params)
