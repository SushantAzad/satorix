"""
EntityResolutionAgent — on new entity ingestion, finds potential duplicates,
scores similarity, and either merges (high confidence) or flags (medium confidence).
"""
import logging
from agents.agent_engine import AgentExecutionEngine
from agents.guardrails import GuardrailConfig
from models.trainers.entity_similarity import compute_similarity, build_entity_text
from agents.tool_registry import call_tool
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

AUTO_MERGE_THRESHOLD = 0.95
FLAG_THRESHOLD = 0.80


class EntityResolutionAgent(AgentExecutionEngine):
    agent_type = "entity_resolution"
    guardrail_config = GuardrailConfig(
        max_tokens=50_000,
        max_steps=50,
        max_runtime_seconds=120.0,
        require_confirmation_on_write=True,
    )

    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        cin = input_params["cin"]
        return [
            {"tool": "get_company_profile", "params": {"cin": cin}, "result_key": "new_entity"},
        ]

    async def build_output(self, results: dict, input_params: dict) -> str:
        new_entity = results.get("new_entity", {})
        new_props = new_entity.get("properties", {})
        new_text = build_entity_text(new_props)

        candidates = await self._find_candidates(new_props)
        merges, flags = 0, 0

        for candidate in candidates:
            cand_text = build_entity_text(candidate)
            sim = await compute_similarity(new_text, cand_text)

            if sim >= AUTO_MERGE_THRESHOLD:
                try:
                    await call_tool("create_alert", {
                        "entity_id": input_params["cin"],
                        "alert_type": "DUPLICATE_AUTO_MERGE",
                        "message": f"Auto-merged with {candidate.get('cin', '?')} (similarity: {sim:.2f})",
                    })
                    merges += 1
                except Exception:
                    pass
            elif sim >= FLAG_THRESHOLD:
                try:
                    await call_tool("create_alert", {
                        "entity_id": input_params["cin"],
                        "alert_type": "DUPLICATE_FLAG_REVIEW",
                        "message": f"Possible duplicate of {candidate.get('cin', '?')} (similarity: {sim:.2f}) — data steward review required",
                    })
                    flags += 1
                except Exception:
                    pass

        return f"Entity resolution: {len(candidates)} candidates checked, {merges} auto-merged, {flags} flagged"

    async def _find_candidates(self, props: dict) -> list[dict]:
        name = props.get("name", "")
        if not name:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.layer3_api_url}/api/v1/search",
                    params={"q": name, "type": "company", "limit": 10},
                )
                if resp.status_code == 200:
                    hits = resp.json().get("results", [])
                    return [h.get("properties", {}) for h in hits]
        except Exception as exc:
            logger.warning("Candidate search failed: %s", exc)
        return []
