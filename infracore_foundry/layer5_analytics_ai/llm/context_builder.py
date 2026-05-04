"""
Builds RBAC-filtered LLM context from ontology objects.
The LLM only sees properties that the requesting actor's role can access.
"""
import json
import logging
from typing import Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# Properties that require elevated role — never exposed to Analyst-level LLM context
SENSITIVE_PROPERTIES = {
    "internalInvestigationNotes",
    "sensitiveFinancialDetails",
    "confidentialSources",
}

ROLE_ALLOWED_PROPERTIES: dict[str, set[str]] = {
    "Admin": set(),        # empty = all allowed
    "Senior_Analyst": {"internalInvestigationNotes"},  # restricted
    "Analyst": SENSITIVE_PROPERTIES,
    "ReadOnly": SENSITIVE_PROPERTIES | {"riskScore", "riskFlags"},
}


def _filter_properties(props: dict, actor_role: str) -> dict:
    restricted = ROLE_ALLOWED_PROPERTIES.get(actor_role, SENSITIVE_PROPERTIES)
    if not restricted:
        return props
    return {k: v for k, v in props.items() if k not in restricted}


async def build_company_context(
    cin: str,
    actor_role: str = "Analyst",
    include_network_summary: bool = True,
) -> dict:
    """Fetches company object from L3 API and returns filtered context dict."""
    ctx: dict = {"cin": cin}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.layer3_api_url}/api/v1/objects/company/{cin}"
            )
            if resp.status_code == 200:
                data = resp.json()
                props = data.get("properties", {})
                ctx["company"] = _filter_properties(props, actor_role)
                ctx["_objects_accessed"] = [f"Company:{cin}"]
    except Exception as exc:
        logger.warning("L3 company context fetch failed for %s: %s", cin, exc)

    if include_network_summary:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.layer4_api_url}/api/v1/network/{cin}",
                    params={"depth": 1},
                )
                if resp.status_code == 200:
                    net = resp.json()
                    ctx["network_node_count"] = net.get("node_count", 0)
                    ctx["network_edge_count"] = net.get("edge_count", 0)
                    ctx["high_risk_neighbours"] = [
                        n["id"] for n in net.get("nodes", [])
                        if (n.get("properties", {}).get("riskScore") or 0) > 70
                    ]
        except Exception as exc:
            logger.warning("L4 network context fetch failed for %s: %s", cin, exc)

    return ctx


def format_context_for_prompt(ctx: dict) -> str:
    """Serialise context to a compact JSON string for prompt injection."""
    return json.dumps(ctx, default=str, indent=2)
