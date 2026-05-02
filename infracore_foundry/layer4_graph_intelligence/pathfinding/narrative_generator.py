"""
NarrativeGenerator — uses claude-sonnet-4-6 with prompt caching to generate
plain-English path explanations for compliance analysts.
"""
import json
import logging
from typing import Optional

import anthropic

from core.config import settings
from core.redis_client import cache_key, cache_get, cache_set

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial intelligence analyst at an Indian corporate intelligence platform.
Given a connection path between two corporate entities, write a concise 2–3 sentence plain-English narrative
that explains the nature of the connection and any risk signals present. Be factual and precise.
Use Indian regulatory terminology (DIN, CIN, CIRP, MCA21, SEBI) where appropriate.
Do not add disclaimers. Output plain text only."""


class NarrativeGenerator:
    def __init__(self) -> None:
        if settings.anthropic_api_key:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:
            self._client = None
            logger.warning("ANTHROPIC_API_KEY not set — narrative generation disabled")

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
        if not self._client:
            return self._fallback_narrative(source_id, target_id, node_path, node_types, hop_details)

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
        user_content = f"""Path: {path_desc}
Hop details: {json.dumps(hop_details, default=str)}
Risk signals detected: {", ".join(signals) if signals else "none"}
Entity properties: {json.dumps(props_summary, default=str)}

Write the narrative:"""

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text.strip()
            await cache_set(ck, {"text": text}, settings.redis_ttl_long)
            return text
        except Exception as exc:
            logger.error("Narrative generation failed: %s", exc)
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
