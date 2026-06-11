"""
GraphIntelligenceAgent — answers open-ended strategic questions about companies
by orchestrating a multi-step tool-use loop grounded in the knowledge graph.

This is the enterprise reasoning system (Gap 3). It extends AgentExecutionEngine
with an LLM-driven tool-use loop:
  1. LLM decides which tools to call (entity lookup, graph traversal, financial
     data, document search, risk signals).
  2. Tool results are fed back to the LLM.
  3. LLM continues until it has enough context or hits the max-iteration guard.
  4. Final synthesis is returned as a well-cited, graph-grounded answer.
"""
import json
import logging
from typing import Any

from shared.llm.provider import LLMMessage, LLMTool, LLMToolResult

from agents.agent_engine import AgentExecutionEngine
from agents.guardrails import GuardrailConfig
from agents.tool_registry import TOOL_REGISTRY, call_tool
from llm.orchestrator import llm_orchestrator

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

# Tools exposed to the LLM in the reasoning loop
REASONING_TOOLS: list[LLMTool] = [
    LLMTool(
        name="get_company_profile",
        description="Fetch the full company profile from the knowledge graph including risk score, flags, status, and financials.",
        input_schema={
            "type": "object",
            "properties": {"cin": {"type": "string", "description": "The company CIN identifier"}},
            "required": ["cin"],
        },
    ),
    LLMTool(
        name="get_network",
        description="Fetch the corporate network around a company — directors, subsidiaries, related entities.",
        input_schema={
            "type": "object",
            "properties": {
                "cin": {"type": "string"},
                "depth": {"type": "integer", "description": "Network depth (1-3)", "default": 2},
            },
            "required": ["cin"],
        },
    ),
    LLMTool(
        name="get_financial_statements",
        description="Fetch the last N years of annual financial statements (revenue, EBITDA, debt, ratios).",
        input_schema={
            "type": "object",
            "properties": {
                "cin": {"type": "string"},
                "years": {"type": "integer", "default": 3},
            },
            "required": ["cin"],
        },
    ),
    LLMTool(
        name="search_documents",
        description="Semantic search over indexed documents (annual reports, board minutes, regulatory filings) for a company.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query"},
                "entity_ref_id": {"type": "string", "description": "CIN of the company"},
                "top_k": {"type": "integer", "default": 4},
            },
            "required": ["query"],
        },
    ),
    LLMTool(
        name="get_entity_features",
        description="Get computed intelligence features (revenue trend, EBITDA margin, debt ratios, CIRP signals) for a company.",
        input_schema={
            "type": "object",
            "properties": {"cin": {"type": "string"}},
            "required": ["cin"],
        },
    ),
    LLMTool(
        name="get_risk_score",
        description="Get the current risk score and risk flags from Layer 3.",
        input_schema={
            "type": "object",
            "properties": {"cin": {"type": "string"}},
            "required": ["cin"],
        },
    ),
]


class GraphIntelligenceAgent(AgentExecutionEngine):
    """
    Reasoning agent for open-ended corporate intelligence questions.

    Usage:
        agent = GraphIntelligenceAgent()
        result = await agent.run({"question": "What is the financial health of...", "cin": "..."})
    """

    agent_type = "graph_intelligence"
    guardrail_config = GuardrailConfig(max_steps=MAX_TOOL_ITERATIONS + 2)

    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        """
        The plan for this agent is dynamic — determined by the LLM tool-use loop.
        We return an empty static plan; the actual reasoning runs in build_output().
        """
        return []

    async def build_output(self, results: dict, input_params: dict) -> str:
        question = input_params.get("question", "")
        cin = input_params.get("cin", "")
        actor_id = input_params.get("actor_id", "system")

        if not question:
            return "No question provided."

        # Seed context with entity profile if CIN provided
        messages: list[LLMMessage] = []
        if cin:
            question_with_context = f"Company CIN: {cin}\n\nQuestion: {question}"
        else:
            question_with_context = question

        messages.append(LLMMessage(role="user", content=question_with_context))

        from llm.prompt_registry import get_prompt
        system_prompt = get_prompt("graph_reasoning_system_v1").system

        tool_call_log: list[dict] = []
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            try:
                response = await llm_orchestrator.complete(
                    messages=messages,
                    workflow_type="graph_intelligence_reasoning",
                    actor_id=actor_id,
                    actor_role="analyst",
                    system=system_prompt,
                    max_tokens=1024,
                    temperature=0.2,
                    tools=REASONING_TOOLS,
                )
            except Exception as exc:
                logger.error("GraphIntelligenceAgent LLM call failed: %s %r", type(exc).__name__, exc)
                return f"[Intelligence engine unavailable — analyst review required for: {question[:100]}]"

            # No tool calls → LLM has finished reasoning
            if not response.tool_calls:
                return response.content or "[No answer generated]"

            # Execute each tool call and append results to the conversation
            tool_results: list[LLMToolResult] = []
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_input = tool_call.input or {}
                logger.info("Agent tool call: %s(%s)", tool_name, list(tool_input.keys()))

                try:
                    result = await call_tool(tool_name, {**tool_input, "actor_id": actor_id})
                except Exception as exc:
                    result = {"error": str(exc)}

                tool_call_log.append({"tool": tool_name, "input": tool_input, "result_summary": str(result)[:200]})
                tool_results.append(LLMToolResult(tool_use_id=tool_call.id, content=json.dumps(result, default=str)))

            # Append assistant message (with tool_use) and tool results to conversation
            messages.append(LLMMessage(role="assistant", content=response.content or "", tool_calls=response.tool_calls))
            messages.append(LLMMessage(role="user", content="", tool_results=tool_results))

        # Exhausted max iterations — ask LLM to synthesize with what it has
        messages.append(LLMMessage(
            role="user",
            content="You have reached the maximum number of tool calls. Synthesize your final answer now based on all data collected so far.",
        ))
        try:
            final = await llm_orchestrator.complete(
                messages=messages,
                workflow_type="graph_intelligence_synthesis",
                actor_id=actor_id,
                actor_role="analyst",
                system=system_prompt,
                max_tokens=1024,
                temperature=0.2,
            )
            return final.content or "[Synthesis failed]"
        except Exception as exc:
            logger.error("Final synthesis failed: %s", exc)
            return "[Intelligence synthesis unavailable — analyst review required]"


graph_intelligence_agent = GraphIntelligenceAgent()
