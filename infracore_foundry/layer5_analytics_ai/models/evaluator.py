"""
Champion/challenger comparison.
Compares a newly trained challenger against the current champion and
returns a promotion recommendation.
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    model_name: str
    champion_metrics: dict
    challenger_metrics: dict
    should_promote: bool
    reason: str


# Minimum thresholds for CIRP precursor model
CIRP_MIN_THRESHOLDS = {
    "auc_roc": 0.75,
    "precision_top_decile": 0.50,
    "recall": 0.65,
}

PROJECT_MIN_THRESHOLDS = {
    "auc_roc": 0.70,
    "precision_top_decile": 0.45,
}

THRESHOLDS_BY_MODEL = {
    "cirp_precursor": CIRP_MIN_THRESHOLDS,
    "project_completion": PROJECT_MIN_THRESHOLDS,
}


def compare(
    model_name: str,
    champion_metrics: Optional[dict],
    challenger_metrics: dict,
) -> EvaluationResult:
    """Returns a promotion decision."""
    thresholds = THRESHOLDS_BY_MODEL.get(model_name, {})

    # Gate 1 — minimum thresholds
    for metric, min_val in thresholds.items():
        challenger_val = challenger_metrics.get(metric, 0.0)
        if challenger_val < min_val:
            return EvaluationResult(
                model_name=model_name,
                champion_metrics=champion_metrics or {},
                challenger_metrics=challenger_metrics,
                should_promote=False,
                reason=f"Challenger {metric}={challenger_val:.3f} below minimum {min_val:.3f}",
            )

    # Gate 2 — must beat champion on primary metric
    primary = "auc_roc"
    if champion_metrics:
        champ_val = champion_metrics.get(primary, 0.0)
        chal_val = challenger_metrics.get(primary, 0.0)
        if chal_val <= champ_val:
            return EvaluationResult(
                model_name=model_name,
                champion_metrics=champion_metrics,
                challenger_metrics=challenger_metrics,
                should_promote=False,
                reason=f"Challenger {primary}={chal_val:.3f} does not improve champion {champ_val:.3f}",
            )
        reason = f"Challenger {primary}={chal_val:.3f} > champion {champ_val:.3f}"
    else:
        reason = "No existing champion — promoting first trained model"

    return EvaluationResult(
        model_name=model_name,
        champion_metrics=champion_metrics or {},
        challenger_metrics=challenger_metrics,
        should_promote=True,
        reason=reason,
    )
