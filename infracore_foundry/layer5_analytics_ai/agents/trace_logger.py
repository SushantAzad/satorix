"""
Execution trace logger — records every step of every agent run.
Persists the full trace to l5_agent_runs.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import get_pool

logger = logging.getLogger(__name__)


class AgentTraceLogger:

    def __init__(self, agent_type: str, actor_id: str, input_params: dict) -> None:
        self.run_id = str(uuid.uuid4())
        self.agent_type = agent_type
        self.actor_id = actor_id
        self.input_params = input_params
        self._steps: list[dict] = []
        self._guardrail_triggers: list[dict] = []
        self._total_tokens = 0
        self._started_at = datetime.now(timezone.utc)

    def record_step(
        self,
        step_number: int,
        tool_name: str,
        tool_params: dict,
        tool_result: Any,
        latency_ms: int,
        tokens_used: int = 0,
    ) -> None:
        self._steps.append({
            "step": step_number,
            "tool": tool_name,
            "params": tool_params,
            "result_summary": _summarize(tool_result),
            "latency_ms": latency_ms,
            "tokens": tokens_used,
        })
        self._total_tokens += tokens_used

    def record_guardrail(self, rule: str, description: str, severity: str) -> None:
        self._guardrail_triggers.append({
            "rule": rule,
            "description": description,
            "severity": severity,
            "at_step": len(self._steps),
        })

    async def finalize(self, status: str, output_summary: str = "") -> None:
        pool = get_pool()
        elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO l5_agent_runs
                        (run_id, agent_type, actor_id, input_params, execution_trace,
                         output_summary, status, total_tokens, total_latency_ms,
                         guardrail_triggers, completed_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10::jsonb, $11)
                    """,
                    self.run_id,
                    self.agent_type,
                    self.actor_id,
                    json.dumps(self.input_params, default=str),
                    json.dumps(self._steps, default=str),
                    output_summary,
                    status,
                    self._total_tokens,
                    int(elapsed * 1000),
                    json.dumps(self._guardrail_triggers, default=str),
                    datetime.now(timezone.utc),
                )
        except Exception as exc:
            logger.error("Agent trace persist failed: %s", exc)

    @property
    def steps(self) -> list[dict]:
        return list(self._steps)


def _summarize(result: Any) -> Any:
    if isinstance(result, dict):
        keys = list(result.keys())[:5]
        return {k: result[k] for k in keys}
    if isinstance(result, str) and len(result) > 200:
        return result[:200] + "..."
    return result
