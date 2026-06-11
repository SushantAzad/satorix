"""Global feature importance tracking — monitors importance stability across training runs."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_feature_importances(clf) -> Optional[dict[str, float]]:
    try:
        if hasattr(clf, "feature_importances_"):
            return {f"feature_{i}": float(v) for i, v in enumerate(clf.feature_importances_)}
        return None
    except Exception as exc:
        logger.warning("Feature importance extraction failed: %s", exc)
        return None


def check_importance_drift(
    current: dict[str, float],
    previous: dict[str, float],
    threshold: float = 0.30,
) -> list[str]:
    """Returns features whose importance shifted by more than `threshold` fraction."""
    drifted = []
    for feat, curr_val in current.items():
        prev_val = previous.get(feat, 0.0)
        if prev_val > 0:
            drift = abs(curr_val - prev_val) / prev_val
            if drift > threshold:
                drifted.append(feat)
    return drifted
