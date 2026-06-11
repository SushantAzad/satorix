"""
NarrativeGenerator — generates plain-English path explanations for compliance analysts.
Uses the Satorix LLM provider abstraction (Anthropic or Ollama based on LLM_PROVIDER env var).
"""
import json
import logging

from shared.llm.provider import get_llm_provider, LLMMessage
from shared.llm.prompt_library import SYSTEM_SATORIX_BASE

from core.config import settings
from core.redis_client import cache_key, cache_get, cache_set

logger = logging.getLogger(__name__)

_NARRATIVE_SYSTEM = (
    SYSTEM_SATORIX_BASE
    + "\n\nGiven a connection path between two corporate entities, write a concise 2–3 sentence "
    "plain-English narrative explaining the nature of the connection and any risk signals present. "
    "Be factual and precise. Use Indian regulatory terminology (DIN, CIN, CIRP, MCA21, SEBI) "
    "where appropriate. Do not add disclaimers. Output plain text only."
)


class NarrativeGenerator:
    def __init__(self) -> None:
        pass  # Provider resolved at call time so runtime env var changes take effect

    async def generate(
        self,
        source_id: str,
        target_id: str,
        node_path: list[str],
        node_types: list[str],
        hop_details: list[dict],
        signals: list[str],
        node_properties: dict[str, dict],
    ) -> str:
        ck = cache_key("narrative", src=source_id, tgt=target_id, path=node_path)
        cached = await cache_get(ck)
        if cached:
            return cached["text"]

        path_desc = " → ".join(
            f"{nid} ({node_types[i] if i < len(node_types) else '?'})"
            for i, nid in enumerate(node_path)
        )
        props_summary = {
            nid: {k: v for k, v in props.items() if k in ("name", "status", "riskScore", "nationality", "isDisqualified")}
            for nid, props in node_properties.items()
            if nid in node_path
        }
        user_content = (
            f"Path: {path_desc}\n"
            f"Hop details: {json.dumps(hop_details, default=str)}\n"
            f"Risk signals detected: {', '.join(signals) if signals else 'none'}\n"
            f"Entity properties: {json.dumps(props_summary, default=str)}\n\n"
            "Write the narrative:"
        )

        try:
            provider = get_llm_provider()
            response = await provider.complete(
                messages=[LLMMessage(role="user", content=user_content)],
                system=_NARRATIVE_SYSTEM,
                max_tokens=256,
                temperature=0.3,
            )
            text = response.content.strip()
            await cache_set(ck, {"text": text}, settings.redis_ttl_long)
            return text
        except Exception as exc:
            logger.error("Narrative generation failed (%s): %s", type(exc).__name__, exc)
            return self._fallback_narrative(source_id, target_id, node_path, node_types, hop_details)

    def _fallback_narrative(
        self,
        source_id: str,
        target_id: str,
        node_path: list[str],
        node_types: list[str],
        hop_details: list[dict],
    ) -> str:
        hops = len(hop_details)
        via = [h.get("via", "?") for h in hop_details]
        return (
            f"{source_id} is connected to {target_id} through a {hops}-hop path "
            f"via {', '.join(via)}. Manual review recommended."
        )
