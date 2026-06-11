"""Tests for data profiling."""

import pytest
import pandas as pd

from layer1_ingestion.profiling.completeness import compute_completeness, compute_dataframe_completeness
from layer1_ingestion.profiling.uniqueness import compute_uniqueness
from layer1_ingestion.profiling.distribution import compute_distribution
from layer1_ingestion.profiling.anomaly_detector import detect_anomalies_zscore, detect_anomalies_iqr


class TestCompleteness:
    def test_full_completeness(self):
        s = pd.Series(["a", "b", "c"])
        result = compute_completeness(s)
        assert result["score"] == 1.0

    def test_partial_completeness(self):
        s = pd.Series(["a", None, "c"])
        result = compute_completeness(s)
        assert 0.5 < result["score"] < 1.0

    def test_null_representation_detection(self):
        s = pd.Series(["a", "N/A", "c", "NULL"])
        result = compute_completeness(s)
        assert result["null_representation"] is not None

    def test_empty_series(self):
        s = pd.Series([], dtype=object)
        result = compute_completeness(s)
        assert result["score"] == 0.0


class TestUniqueness:
    def test_all_unique(self):
        s = pd.Series([1, 2, 3, 4, 5])
        result = compute_uniqueness(s)
        assert result["score"] == 1.0
        assert result["duplicate_count"] == 0

    def test_with_duplicates(self):
        s = pd.Series([1, 1, 2, 2, 3])
        result = compute_uniqueness(s)
        assert result["score"] < 1.0
        assert result["duplicate_count"] > 0


class TestDistribution:
    def test_numeric_distribution(self):
        s = pd.Series([10, 20, 30, 40, 50])
        result = compute_distribution(s)
        assert result["min"] == 10.0
        assert result["max"] == 50.0
        assert result["mean"] == 30.0

    def test_string_distribution(self):
        s = pd.Series(["a", "b", "c", "a", "b"])
        result = compute_distribution(s)
        assert len(result["top_values"]) > 0


class TestAnomalyDetection:
    def test_zscore_no_anomalies(self):
        s = pd.Series(range(100))
        flags = detect_anomalies_zscore(s)
        assert len(flags) == 0

    def test_zscore_with_anomalies(self):
        values = list(range(100)) + [10000]
        s = pd.Series(values)
        flags = detect_anomalies_zscore(s)
        assert len(flags) > 0

    def test_iqr_with_anomalies(self):
        values = list(range(100)) + [10000]
        s = pd.Series(values)
        flags = detect_anomalies_iqr(s)
        assert len(flags) > 0
