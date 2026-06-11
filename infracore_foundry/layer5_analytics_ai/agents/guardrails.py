"""
Guardrails — conditions that pause agent execution and require human confirmation.
"""
from dataclasses import dataclass, field


@dataclass
class GuardrailViolation:
    rule: str
    description: str
    severity: str  # WARNING | HALT


@dataclass
class GuardrailConfig:
    max_tokens: int = 50_000
    max_steps: int = 20
    max_runtime_seconds: float = 120.0
    high_risk_threshold: float = 0.85
    require_confirmation_on_write: bool = True


def check_guardrails(
    config: GuardrailConfig,
    step_number: int,
    total_tokens: int,
    elapsed_seconds: float,
    last_tool: str,
    last_result: object,
) -> list[GuardrailViolation]:
    violations: list[GuardrailViolation] = []

    if total_tokens >= config.max_tokens:
        violations.append(GuardrailViolation(
            rule="token_budget",
            description=f"Token budget exceeded: {total_tokens} >= {config.max_tokens}",
            severity="HALT",
        ))

    if step_number >= config.max_steps:
        violations.append(GuardrailViolation(
            rule="step_limit",
            description=f"Step limit reached: {step_number} >= {config.max_steps}",
            severity="HALT",
        ))

    if elapsed_seconds >= config.max_runtime_seconds:
        violations.append(GuardrailViolation(
            rule="runtime_limit",
            description=f"Runtime limit exceeded: {elapsed_seconds:.1f}s",
            severity="HALT",
        ))

    # Check CIRP prediction result for high-confidence signal
    if isinstance(last_result, dict):
        pred = last_result.get("prediction_value")
        if pred is not None and float(pred) >= config.high_risk_threshold:
            violations.append(GuardrailViolation(
                rule="high_cirp_risk",
                description=f"High CIRP risk detected: {pred:.0%} — analyst confirmation required",
                severity="WARNING",
            ))

        # Writes to ontology require confirmation
        if config.require_confirmation_on_write and last_tool in ("create_alert", "generate_report"):
            violations.append(GuardrailViolation(
                rule="ontology_write",
                description=f"Tool '{last_tool}' will write to ontology — confirmation required",
                severity="WARNING",
            ))

    return violations
