"""
Path narrative workflow — replaces the direct Anthropic call in Layer 4's NarrativeGenerator.
L4's NarrativeGenerator now delegates here via HTTP call to the L5 API.
"""
import json
from llm.orchestrator import llm_orchestrator


async def generate_path_narrative(
    source_id: str,
    target_id: str,
    node_path: list[str],
    node_types: list[str],
    hop_details: list[dict],
    signals: list[str],
    node_properties: dict[str, dict],
    actor_id: str = "system",
    actor_role: str = "system",
) -> str:
    path_desc = " → ".join(
        f"{nid} ({node_types[i] if i < len(node_types) else '?'})"
        for i, nid in enumerate(node_path)
    )
    props_summary = {
        nid: {k: v for k, v in props.items() if k in ("name", "status", "riskScore", "nationality")}
        for nid, props in node_properties.items()
        if nid in node_path
    }
    objects_accessed = [f"Entity:{nid}" for nid in node_path]

    return await llm_orchestrator.run(
        prompt_key="narrative_v1",
        format_kwargs={
            "path_desc": path_desc,
            "hop_details": json.dumps(hop_details, default=str),
            "signals": ", ".join(signals) if signals else "none",
            "entity_props": json.dumps(props_summary, default=str),
        },
        actor_id=actor_id,
        actor_role=actor_role,
        objects_accessed=objects_accessed,
        output_disposition="returned",
        max_tokens=256,
        workflow_type="narrative",
    )
