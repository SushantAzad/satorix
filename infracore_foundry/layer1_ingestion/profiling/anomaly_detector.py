"""Statistical anomaly detection using z-scores and IQR."""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def detect_anomalies_zscore(series: pd.Series, threshold: float = 3.0) -> list[str]:
    """Detect anomalies using z-score method."""
    flags = []
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 10:
        return flags
    mean = numeric.mean()
    std = numeric.std()
    if std == 0:
        return flags
    z_scores = (numeric - mean) / std
    outlier_count = (z_scores.abs() > threshold).sum()
    if outlier_count > 0:
        pct = outlier_count / len(numeric) * 100
        flags.append(f"z-score outliers: {outlier_count} values ({pct:.1f}%) exceed {threshold} sigma")
    return flags


def detect_anomalies_iqr(series: pd.Series, factor: float = 1.5) -> list[str]:
    """Detect anomalies using IQR method."""
    flags = []
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 10:
        return flags
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return flags
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    outliers = ((numeric < lower) | (numeric > upper)).sum()
    if outliers > 0:
        flags.append(f"IQR outliers: {outliers} values outside [{lower:.2f}, {upper:.2f}]")
    return flags


def detect_volume_anomaly(current_count: int, historical_counts: list[int]) -> bool:
    """Detect if current record count is outside 3-sigma of historical average."""
    if len(historical_counts) < 5:
        return False
    mean = np.mean(historical_counts)
    std = np.std(historical_counts)
    if std == 0:
        return current_count != mean
    z = abs(current_count - mean) / std
    return z > 3.0


def detect_column_anomalies(series: pd.Series) -> list[str]:
    """Run all anomaly detection methods on a column."""
    flags = []
    flags.extend(detect_anomalies_zscore(series))
    flags.extend(detect_anomalies_iqr(series))
    return flags
