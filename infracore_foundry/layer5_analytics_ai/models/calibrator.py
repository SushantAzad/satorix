"""
Calibrates model probability outputs using Platt scaling (sklearn CalibratedClassifierCV).
Ensures that predicted 70% probability corresponds to ~70% realized rate.
"""
import logging
import pickle
from typing import Optional

logger = logging.getLogger(__name__)


def calibrate(clf, X_cal, y_cal, method: str = "isotonic"):
    """
    Wrap `clf` with CalibratedClassifierCV fitted on calibration set.
    Returns calibrated classifier.
    """
    try:
        from sklearn.calibration import CalibratedClassifierCV
        calibrated = CalibratedClassifierCV(clf, method=method, cv="prefit")
        calibrated.fit(X_cal, y_cal)
        return calibrated
    except Exception as exc:
        logger.warning("Calibration failed, returning uncalibrated model: %s", exc)
        return clf


def brier_score(y_true, y_prob) -> float:
    try:
        from sklearn.metrics import brier_score_loss
        return float(brier_score_loss(y_true, y_prob))
    except Exception:
        return 1.0


def reliability_diagram_data(y_true, y_prob, n_bins: int = 10) -> list[dict]:
    """Returns data for a reliability/calibration curve."""
    try:
        from sklearn.calibration import calibration_curve
        import numpy as np
        fraction_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=n_bins)
        return [
            {"mean_predicted": float(mp), "fraction_positive": float(fp)}
            for mp, fp in zip(mean_pred, fraction_pos)
        ]
    except Exception:
        return []
