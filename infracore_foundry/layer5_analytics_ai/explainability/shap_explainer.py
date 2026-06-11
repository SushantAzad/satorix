"""
SHAP value computation for XGBoost models.
Called by ModelServingEngine; also available standalone for batch explanation jobs.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_shap_values(clf, X_np, feature_names: list[str]) -> Optional[dict]:
    try:
        import shap
        explainer = shap.TreeExplainer(clf)
        shap_vals = explainer.shap_values(X_np)
        if isinstance(shap_vals, list):
            vals = shap_vals[1][0]
        else:
            vals = shap_vals[0]
        return {feature_names[i]: round(float(vals[i]), 5) for i in range(len(feature_names))}
    except ImportError:
        logger.warning("shap not installed — SHAP explanations disabled")
        return None
    except Exception as exc:
        logger.warning("SHAP computation failed: %s", exc)
        return None


def format_shap_explanation(shap_values: dict, top_n: int = 5) -> str:
    """Format SHAP values into a human-readable explanation string."""
    if not shap_values:
        return "Feature contributions not available."

    sorted_feats = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:top_n]
    positive = [(f, v) for f, v in sorted_feats if v > 0]
    negative = [(f, v) for f, v in sorted_feats if v < 0]

    parts = []
    if positive:
        drivers = ", ".join(f"{f.replace('_', ' ')} (+{v:.3f})" for f, v in positive)
        parts.append(f"Risk drivers: {drivers}")
    if negative:
        mitigants = ", ".join(f"{f.replace('_', ' ')} ({v:.3f})" for f, v in negative)
        parts.append(f"Mitigating factors: {mitigants}")

    return ". ".join(parts) + "." if parts else "No significant feature contributions."
