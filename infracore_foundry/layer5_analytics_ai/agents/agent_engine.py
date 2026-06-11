"""
AgentExecutionEngine — base class for all Layer 5 agents.
Provides the step-by-step execution loop with guardrail checking and trace logging.

Subclasses that need LLM calls should use self._get_llm_provider() rather than
instantiating providers directly. This ensures runtime provider switching works.
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from shared.llm.provider import get_llm_provider, BaseLLMProvider, LLMMessage

from agents.guardrails import GuardrailConfig, GuardrailViolation, check_guardrails
from agents.trace_logger import AgentTraceLogger
from agents.tool_registry import call_tool

logger = logging.getLogger(__name__)


class AgentExecutionEngine(ABC):
    """
    Subclass and implement `build_plan()` to define the agent's step sequence.
    The engine executes steps, enforces guardrails, and logs the full trace.
    """

    agent_type: str = "base"
    guardrail_config: GuardrailConfig = GuardrailConfig()

    async def run(self, input_params: dict, actor_id: str = "system") -> dict:
        tracer = AgentTraceLogger(self.agent_type, actor_id, input_params)
        t_start = time.monotonic()
        total_tokens = 0
        step_number = 0
        guardrail_halted = False

        plan = await self.build_plan(input_params, actor_id)
        results: dict[str, Any] = {}

        for step in plan:
            tool_name = step["tool"]
            tool_params = {**step.get("params", {}), "actor_id": actor_id}
            step_number += 1
            t_step = time.monotonic()

            try:
                result = await call_tool(tool_name, tool_params)
            except Exception as exc:
                logger.error("Agent step %d tool=%s failed: %s", step_number, tool_name, exc)
                result = {"error": str(exc)}

            latency_ms = int((time.monotonic() - t_step) * 1000)
            tracer.record_step(step_number, tool_name, tool_params, result, latency_ms)
            results[step.get("result_key", tool_name)] = result

            elapsed = time.monotonic() - t_start
            violations = check_guardrails(
                self.guardrail_config,
                step_number,
                total_tokens,
                elapsed,
                tool_name,
                result,
            )
            for v in violations:
                tracer.record_guardrail(v.rule, v.description, v.severity)
                logger.warning("Guardrail [%s]: %s", v.severity, v.description)
                if v.severity == "HALT":
                    guardrail_halted = True
                    break
            if guardrail_halted:
                break

        output_summary = await self.build_output(results, input_params)
        status = "halted" if guardrail_halted else "completed"
        await tracer.finalize(status, output_summary)

        return {
            "run_id": tracer.run_id,
            "agent_type": self.agent_type,
            "status": status,
            "output": output_summary,
            "results": results,
            "guardrail_halted": guardrail_halted,
        }

    @abstractmethod
    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        """Return list of {tool, params, result_key} dicts defining execution steps."""

    async def build_output(self, results: dict, input_params: dict) -> str:
        """
        Generate a final output summary.
        Subclasses can override this and use self._get_llm_provider() to generate
        LLM-powered summaries of the agent's execution results.
        """
        return f"Agent {self.agent_type} completed with {len(results)} steps"

    def _get_llm_provider(self) -> BaseLLMProvider:
        """Returns the active LLM provider. Resolved at call time — never cached."""
        return get_llm_provider()
