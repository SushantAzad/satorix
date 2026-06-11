"""
RegulatoryWatchAgent — runs when new regulatory actions are published,
identifies affected entities in client watchlists, and generates alerts.
"""
import logging
from agents.agent_engine import AgentExecutionEngine
from agents.guardrails import GuardrailConfig
from agents.tool_registry import call_tool
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class RegulatoryWatchAgent(AgentExecutionEngine):
    agent_type = "regulatory_watch"
    guardrail_config = GuardrailConfig(
        max_tokens=100_000,
        max_steps=100,
        max_runtime_seconds=600.0,
        require_confirmation_on_write=False,
    )

    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        affected_cins = input_params.get("affected_cins", [])
        return [
            {"tool": "get_company_profile", "params": {"cin": cin}, "result_key": f"profile_{cin}"}
            for cin in affected_cins
        ]

    async def build_output(self, results: dict, input_params: dict) -> str:
        regulatory_action = input_params.get("regulatory_action", {})
        affected_cins = input_params.get("affected_cins", [])
        alerts_created = 0

        for cin in affected_cins:
            try:
                await call_tool("create_alert", {
                    "entity_id": cin,
                    "alert_type": "REGULATORY_ACTION",
                    "message": (
                        f"New regulatory action: {regulatory_action.get('action_type', 'Unknown')} "
                        f"by {regulatory_action.get('regulator', 'Unknown regulator')}"
                    ),
                })
                alerts_created += 1
            except Exception as exc:
                logger.warning("Alert creation failed for %s: %s", cin, exc)

        return f"Regulatory watch: {len(affected_cins)} entities affected, {alerts_created} alerts created"
