"""
Main data profiler orchestrator.
Produces comprehensive ProfileReport for any DataFrame.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from layer1_ingestion.profiling.completeness import compute_completeness
from layer1_ingestion.profiling.uniqueness import compute_uniqueness
from layer1_ingestion.profiling.distribution import compute_distribution
from layer1_ingestion.profiling.anomaly_detector import detect_column_anomalies
from layer1_ingestion.profiling.consistency_rules import run_all_rules, ConsistencyViolation

logger = logging.getLogger(__name__)


@dataclass
class ColumnProfile:
    column_name: str
    detected_type: str
    indian_identifier_type: Optional[str]
    completeness_score: float
    uniqueness_score: float
    pattern_conformance: Optional[float]
    min_value: Any
    max_value: Any
    mean_value: Optional[float]
    top_values: list[tuple[Any, int]]
    anomaly_flags: list[str]
    null_representation: Optional[str]

    @property
    def null_percentage(self) -> float:
        return round((1.0 - self.completeness_score) * 100, 2)


@dataclass
class ConsistencyIssue:
    rule_name: str
    affected_columns: list[str]
    violation_count: int
    sample_violations: list[dict]
    severity: str


@dataclass
class ProfileReport:
    source_id: str
    profiled_at: datetime
    total_records: int
    total_columns: int
    column_profiles: dict[str, ColumnProfile]
    cross_field_issues: list[ConsistencyIssue]
    overall_quality_score: float
    recommendations: list[str]

    @property
    def columns(self):
        return list(self.column_profiles.values())


class DataProfiler:
    """Main profiling orchestrator."""

    def profile(self, df: pd.DataFrame, source_id: str = "") -> ProfileReport:
        """Generate a comprehensive profile report for a DataFrame."""
        logger.info("Starting profiling for source %s (%d rows, %d cols)", source_id, len(df), len(df.columns))

        # Detect Indian identifiers
        indian_ids: dict = {}
        try:
            from layer1_ingestion.schema.indian_identifiers import detect_identifier_columns
            indian_ids = detect_identifier_columns(df)
        except ImportError:
            pass

        column_profiles: dict[str, ColumnProfile] = {}
        for col in df.columns:
            series = df[col]
            completeness = compute_completeness(series)
            uniqueness = compute_uniqueness(series)
            distribution = compute_distribution(series)
            anomalies = detect_column_anomalies(series)

            # Pattern conformance for Indian identifiers
            pattern_conf = None
            id_type = indian_ids.get(str(col))
            if id_type:
                from layer1_ingestion.schema.indian_identifiers import VALIDATORS
                validator = VALIDATORS.get(id_type)
                if validator:
                    sample = series.dropna().astype(str).head(500)
                    if len(sample) > 0:
                        valid = sum(1 for v in sample if validator.is_valid(v))
                        pattern_conf = round(valid / len(sample), 4)

            cp = ColumnProfile(
                column_name=str(col),
                detected_type=str(series.dtype),
                indian_identifier_type=id_type,
                completeness_score=completeness["score"],
                uniqueness_score=uniqueness["score"],
                pattern_conformance=pattern_conf,
                min_value=distribution.get("min"),
                max_value=distribution.get("max"),
                mean_value=distribution.get("mean"),
                top_values=distribution.get("top_values", []),
                anomaly_flags=anomalies,
                null_representation=completeness.get("null_representation"),
            )
            column_profiles[str(col)] = cp

        # Consistency rules
        violations = run_all_rules(df)
        cross_field_issues = [
            ConsistencyIssue(
                rule_name=v.rule_name,
                affected_columns=v.affected_columns,
                violation_count=v.violation_count,
                sample_violations=v.sample_violations,
                severity=v.severity,
            )
            for v in violations
        ]

        # Overall quality score (0-100)
        quality_score = self._compute_quality_score(column_profiles, cross_field_issues, len(df))

        # Recommendations
        recommendations = self._generate_recommendations(column_profiles, cross_field_issues)

        report = ProfileReport(
            source_id=source_id,
            profiled_at=datetime.now(timezone.utc),
            total_records=len(df),
            total_columns=len(df.columns),
            column_profiles=column_profiles,
            cross_field_issues=cross_field_issues,
            overall_quality_score=quality_score,
            recommendations=recommendations,
        )
        logger.info("Profiling complete: score=%.1f, issues=%d", quality_score, len(cross_field_issues))
        return report

    def _compute_quality_score(
        self,
        profiles: dict[str, ColumnProfile],
        issues: list[ConsistencyIssue],
        total_records: int,
    ) -> float:
        if not profiles:
            return 0.0

        # Completeness: 40% weight
        avg_completeness = sum(p.completeness_score for p in profiles.values()) / len(profiles)

        # Uniqueness: 20% weight (for non-text columns)
        uniqueness_scores = [p.uniqueness_score for p in profiles.values() if p.uniqueness_score > 0]
        avg_uniqueness = sum(uniqueness_scores) / len(uniqueness_scores) if uniqueness_scores else 1.0

        # Pattern conformance: 20% weight (for identified columns)
        pattern_scores = [p.pattern_conformance for p in profiles.values() if p.pattern_conformance is not None]
        avg_pattern = sum(pattern_scores) / len(pattern_scores) if pattern_scores else 1.0

        # Consistency: 20% weight
        critical_issues = sum(1 for i in issues if i.severity == "critical")
        warning_issues = sum(1 for i in issues if i.severity == "warning")
        consistency_penalty = min(1.0, (critical_issues * 0.2 + warning_issues * 0.05))
        consistency_score = max(0.0, 1.0 - consistency_penalty)

        score = (avg_completeness * 40 + avg_uniqueness * 20 + avg_pattern * 20 + consistency_score * 20)
        return round(min(100.0, max(0.0, score)), 1)

    def _generate_recommendations(
        self,
        profiles: dict[str, ColumnProfile],
        issues: list[ConsistencyIssue],
    ) -> list[str]:
        recs = []
        for col, p in profiles.items():
            if p.completeness_score < 0.8:
                recs.append(f"Column '{col}' has {(1-p.completeness_score)*100:.0f}% missing values — investigate data source")
            if p.null_representation:
                recs.append(f"Column '{col}' uses '{p.null_representation}' as null — standardize to proper NULL")
            if p.pattern_conformance is not None and p.pattern_conformance < 0.9:
                recs.append(f"Column '{col}' ({p.indian_identifier_type}): {(1-p.pattern_conformance)*100:.0f}% invalid format")
            if p.anomaly_flags:
                recs.append(f"Column '{col}' has anomalies: {'; '.join(p.anomaly_flags[:2])}")
        for issue in issues:
            if issue.severity == "critical":
                recs.append(f"CRITICAL: {issue.rule_name} — {issue.violation_count} violations found")
        return recs[:20]
