"""
PortfolioMonitorAgent — nightly agent that checks all portfolio companies
for new risk signals and creates alerts for threshold crossings.
"""
import logging
from agents.agent_engine import AgentExecutionEngine
from agents.guardrails import GuardrailConfig
from agents.tool_registry import call_tool
from agents.trace_logger import AgentTraceLogger
import time

logger = logging.getLogger(__name__)


class PortfolioMonitorAgent(AgentExecutionEngine):
    agent_type = "portfolio_monitor"
    guardrail_config = GuardrailConfig(
        max_tokens=200_000,
        max_steps=500,
        max_runtime_seconds=3600.0,
        high_risk_threshold=0.80,
        require_confirmation_on_write=False,  # Auto-create alerts in nightly run
    )

    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        portfolio_cins = input_params.get("portfolio_cins", [])
        # One risk-score fetch per company; alerts created in build_output
        return [
            {"tool": "get_risk_score", "params": {"cin": cin}, "result_key": f"risk_{cin}"}
            for cin in portfolio_cins
        ]

    async def build_output(self, results: dict, input_params: dict) -> str:
        alerts_created = 0
        risk_threshold = input_params.get("alert_threshold", 70)

        for key, result in results.items():
            if not key.startswith("risk_"):
                continue
            cin = key[5:]
            score = result.get("risk_score") or result.get("score", 0)
            if isinstance(score, (int, float)) and score >= risk_threshold:
                try:
                    await call_tool("create_alert", {
                        "entity_id": cin,
                        "alert_type": "HIGH_RISK_SCORE",
                        "message": f"Risk score {score}/100 exceeds threshold {risk_threshold}",
                    })
                    alerts_created += 1
                except Exception as exc:
                    logger.warning("Alert creation failed for %s: %s", cin, exc)

        return f"Portfolio monitor: {len(results)} companies checked, {alerts_created} alerts created"
