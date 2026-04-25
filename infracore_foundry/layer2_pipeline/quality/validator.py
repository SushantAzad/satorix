"""
Data quality validation engine.
Applies QualityRule objects to a DataFrame using 4 failure policies.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.quality.rules import FailurePolicy, QualityRule, RuleSeverity

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    rule_id: str
    column: str | None
    total_rows: int
    failing_rows: int
    severity: str
    failure_policy: str

    @property
    def pass_rate(self) -> float:
        if self.total_rows == 0:
            return 1.0
        return 1.0 - (self.failing_rows / self.total_rows)


class DataQualityValidator:
    """
    Applies a list of QualityRules to a DataFrame.
    Returns the (possibly modified) DataFrame and a list of ValidationResult objects.
    """

    def __init__(self, named_frames: dict[str, pd.DataFrame] | None = None) -> None:
        self.named_frames = named_frames or {}

    def validate(
        self,
        df: pd.DataFrame,
        rules: list[QualityRule],
        context: ExecutionContext,
        step_id: str,
    ) -> tuple[pd.DataFrame, list[ValidationResult]]:
        results: list[ValidationResult] = []
        df = df.copy()

        for rule in rules:
            df, result = self._apply_rule(df, rule, context, step_id)
            results.append(result)

        return df, results

    def _apply_rule(
        self,
        df: pd.DataFrame,
        rule: QualityRule,
        context: ExecutionContext,
        step_id: str,
    ) -> tuple[pd.DataFrame, ValidationResult]:
        # Compute the failing mask
        try:
            failing_mask = self._compute_failing_mask(df, rule)
        except Exception as exc:
            logger.warning("Rule %s failed to evaluate: %s", rule.rule_id, exc)
            context.warn(f"Quality rule {rule.rule_id} evaluation error: {exc}")
            return df, ValidationResult(
                rule_id=rule.rule_id, column=rule.column,
                total_rows=len(df), failing_rows=0,
                severity=rule.severity.value, failure_policy=rule.failure_policy.value,
            )

        failing_count = int(failing_mask.sum())
        if failing_count == 0:
            return df, ValidationResult(
                rule_id=rule.rule_id, column=rule.column,
                total_rows=len(df), failing_rows=0,
                severity=rule.severity.value, failure_policy=rule.failure_policy.value,
            )

        # Log failing records to context
        if rule.severity == RuleSeverity.ERROR:
            for _, row in df[failing_mask].head(10).iterrows():
                context.add_failed_record(
                    step_id=step_id,
                    error_type="transform",
                    error_subtype=f"quality_rule_{rule.rule_type}",
                    error_message=f"Rule {rule.rule_id!r} failed on column {rule.column!r}",
                    severity=rule.severity.value,
                    original_record=row.to_dict(),
                )

        # Apply failure policy
        df = self._apply_policy(df, rule, failing_mask)

        return df, ValidationResult(
            rule_id=rule.rule_id, column=rule.column,
            total_rows=len(df) + (failing_count if rule.failure_policy == FailurePolicy.REJECT else 0),
            failing_rows=failing_count,
            severity=rule.severity.value, failure_policy=rule.failure_policy.value,
        )

    def _compute_failing_mask(self, df: pd.DataFrame, rule: QualityRule) -> pd.Series:
        """Return boolean Series — True where the row FAILS the rule."""
        col = rule.column
        params = rule.parameters

        if rule.rule_type == "not_null":
            return df[col].isna()

        elif rule.rule_type == "not_empty":
            return df[col].isna() | (df[col].astype(str).str.strip() == "")

        elif rule.rule_type == "regex":
            pattern = params["pattern"]
            return ~df[col].astype(str).str.match(pattern, na=False)

        elif rule.rule_type == "range":
            series = pd.to_numeric(df[col], errors="coerce")
            mask = pd.Series(False, index=df.index)
            if params.get("min") is not None:
                mask |= series < params["min"]
            if params.get("max") is not None:
                mask |= series > params["max"]
            mask |= series.isna() & df[col].notna()  # non-numeric values that should be numeric
            return mask

        elif rule.rule_type == "in_set":
            allowed = set(params["allowed"])
            return ~df[col].isin(allowed) & df[col].notna()

        elif rule.rule_type == "referential":
            ref_frame_name = params["ref_frame"]
            ref_col = params["ref_column"]
            if ref_frame_name not in self.named_frames:
                logger.warning("Referential rule %s: ref_frame %r not available", rule.rule_id, ref_frame_name)
                return pd.Series(False, index=df.index)
            ref_values = set(self.named_frames[ref_frame_name][ref_col].dropna().astype(str))
            return ~df[col].astype(str).isin(ref_values) & df[col].notna()

        elif rule.rule_type == "custom_expr":
            expression = params["expression"]
            # Rows that match the expression ARE the failing rows
            try:
                return df.eval(expression)
            except Exception as exc:
                raise ValueError(f"custom_expr failed: {expression!r}: {exc}") from exc

        else:
            raise ValueError(f"Unknown rule type: {rule.rule_type!r}")

    def _apply_policy(
        self, df: pd.DataFrame, rule: QualityRule, failing_mask: pd.Series
    ) -> pd.DataFrame:
        policy = rule.failure_policy
        col = rule.column

        if policy == FailurePolicy.REJECT:
            return df[~failing_mask].reset_index(drop=True)

        elif policy == FailurePolicy.FLAG:
            flag_col = f"_failed_{rule.rule_id}"
            df[flag_col] = failing_mask
            return df

        elif policy == FailurePolicy.DEFAULT:
            if col is not None and col in df.columns:
                df.loc[failing_mask, col] = rule.default_value
            return df

        elif policy == FailurePolicy.TRANSFORM:
            # Not applicable at this level — handled by the pipeline step
            return df

        return df
