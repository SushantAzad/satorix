"""
DueDiligenceAgent — orchestrates a full corporate due diligence workflow.
Steps: profile → network → risk scores → CIRP prediction → path narratives → benchmark → report.
"""
from agents.agent_engine import AgentExecutionEngine
from agents.guardrails import GuardrailConfig


class DueDiligenceAgent(AgentExecutionEngine):
    agent_type = "due_diligence"
    guardrail_config = GuardrailConfig(
        max_tokens=80_000,
        max_steps=15,
        max_runtime_seconds=180.0,
        high_risk_threshold=0.85,
        require_confirmation_on_write=True,
    )

    async def build_plan(self, input_params: dict, actor_id: str) -> list[dict]:
        cin = input_params["cin"]
        depth = input_params.get("depth", 2)
        return [
            {"tool": "get_company_profile", "params": {"cin": cin}, "result_key": "profile"},
            {"tool": "get_network", "params": {"cin": cin, "depth": depth}, "result_key": "network"},
            {"tool": "get_risk_score", "params": {"cin": cin}, "result_key": "risk"},
            {"tool": "get_cirp_prediction", "params": {"cin": cin}, "result_key": "cirp"},
            {"tool": "run_benchmark", "params": {"cin": cin}, "result_key": "benchmark"},
            {"tool": "generate_report", "params": {"cin": cin, "actor_id": actor_id}, "result_key": "report"},
        ]

    async def build_output(self, results: dict, input_params: dict) -> str:
        profile = results.get("profile", {})
        name = profile.get("properties", {}).get("name", input_params.get("cin"))
        cirp = results.get("cirp", {})
        prob = cirp.get("prediction_value", "N/A")
        report_id = results.get("report", {}).get("report_id", "")
        return (
            f"Due diligence completed for {name}. "
            f"CIRP probability: {prob:.1%} " if isinstance(prob, float) else f"CIRP probability: {prob}. "
            f"Report ID: {report_id}"
        )
