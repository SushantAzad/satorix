"""
Quality rule definitions.
Rules are declarative dicts; the validator engine interprets them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FailurePolicy(str, Enum):
    REJECT = "reject"        # Drop the row entirely
    FLAG = "flag"            # Keep row, add _failed_<rule> column = True
    DEFAULT = "default"      # Replace failing value with a default
    TRANSFORM = "transform"  # Apply a corrective expression


class RuleSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class QualityRule:
    """A single data quality rule."""
    rule_id: str
    rule_type: str           # not_null | not_empty | regex | range | in_set | custom_expr | referential
    column: Optional[str]    # None for row-level rules
    severity: RuleSeverity = RuleSeverity.ERROR
    failure_policy: FailurePolicy = FailurePolicy.FLAG
    default_value: Any = None
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "QualityRule":
        return cls(
            rule_id=d["rule_id"],
            rule_type=d["rule_type"],
            column=d.get("column"),
            severity=RuleSeverity(d.get("severity", "error")),
            failure_policy=FailurePolicy(d.get("failure_policy", "flag")),
            default_value=d.get("default_value"),
            parameters=d.get("parameters", {}),
            description=d.get("description", ""),
        )


# ── Standard rule builders (convenience functions for YAML pipeline authors) ──

def not_null(column: str, policy: str = "flag", severity: str = "error") -> dict:
    return {
        "rule_id": f"not_null_{column}",
        "rule_type": "not_null",
        "column": column,
        "severity": severity,
        "failure_policy": policy,
    }


def not_empty(column: str, policy: str = "flag") -> dict:
    return {
        "rule_id": f"not_empty_{column}",
        "rule_type": "not_empty",
        "column": column,
        "severity": "error",
        "failure_policy": policy,
    }


def regex_match(column: str, pattern: str, policy: str = "flag", severity: str = "error") -> dict:
    return {
        "rule_id": f"regex_{column}",
        "rule_type": "regex",
        "column": column,
        "severity": severity,
        "failure_policy": policy,
        "parameters": {"pattern": pattern},
    }


def value_range(
    column: str, min_val: Any = None, max_val: Any = None,
    policy: str = "flag", severity: str = "error",
) -> dict:
    return {
        "rule_id": f"range_{column}",
        "rule_type": "range",
        "column": column,
        "severity": severity,
        "failure_policy": policy,
        "parameters": {"min": min_val, "max": max_val},
    }


def in_set(column: str, allowed: list, policy: str = "flag") -> dict:
    return {
        "rule_id": f"in_set_{column}",
        "rule_type": "in_set",
        "column": column,
        "severity": "error",
        "failure_policy": policy,
        "parameters": {"allowed": allowed},
    }


def referential_integrity(
    column: str, ref_column: str, ref_frame: str, policy: str = "flag",
) -> dict:
    return {
        "rule_id": f"ref_{column}",
        "rule_type": "referential",
        "column": column,
        "severity": "error",
        "failure_policy": policy,
        "parameters": {"ref_frame": ref_frame, "ref_column": ref_column},
    }


def custom_expression(rule_id: str, expression: str, policy: str = "flag", severity: str = "warning") -> dict:
    """Row-level rule using a pandas query expression that must return False for passing rows."""
    return {
        "rule_id": rule_id,
        "rule_type": "custom_expr",
        "column": None,
        "severity": severity,
        "failure_policy": policy,
        "parameters": {"expression": expression},
    }


# ── Pre-built rule sets for Infracore entity types ──

COMPANY_RULES: list[dict] = [
    not_null("cin", policy="reject"),
    regex_match("cin", r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$", severity="error"),
    not_null("company_name", policy="flag"),
    in_set("company_status", ["Active", "Strike Off", "Under Liquidation", "Dissolved", "Amalgamated"]),
    regex_match("pan", r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", severity="warning"),
    regex_match("gstin", r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$", severity="warning"),
    not_null("registration_date", policy="flag"),
]

DIRECTOR_RULES: list[dict] = [
    not_null("din", policy="reject"),
    regex_match("din", r"^\d{8}$"),
    not_null("director_name"),
    not_null("cin", policy="flag"),
    in_set("director_status", ["Active", "Disqualified", "Resigned", "Deceased"]),
]

FINANCIAL_RULES: list[dict] = [
    not_null("cin", policy="reject"),
    not_null("financial_year"),
    value_range("paid_up_capital", min_val=0),
    value_range("authorised_capital", min_val=0),
    custom_expression(
        "authorised_gte_paidup",
        "authorised_capital < paid_up_capital",  # rows that FAIL this are flagged
        policy="flag",
        severity="warning",
    ),
]
