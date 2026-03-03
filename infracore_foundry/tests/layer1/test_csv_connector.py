"""Tests for the CSV connector."""

import pytest
import pandas as pd

from layer1_ingestion.connectors.csv_connector import CSVConnector
from layer1_ingestion.connectors.base_connector import ExtractionConfig


class TestCSVConnector:
    def test_extract_local_csv(self, sample_csv_data):
        connector = CSVConnector("test", {"file_path": sample_csv_data, "source": "local"})
        config = ExtractionConfig(source_id="test", client_id="test_client")
        df = connector.extract_full(config)
        assert len(df) == 3
        assert "name" in df.columns
        assert "city" in df.columns

    def test_connection_test(self, sample_csv_data):
        connector = CSVConnector("test", {"file_path": sample_csv_data, "source": "local"})
        result = connector.test_connection()
        assert result.success is True

    def test_connection_test_missing_file(self):
        connector = CSVConnector("test", {"file_path": "/nonexistent.csv", "source": "local"})
        result = connector.test_connection()
        assert result.success is False

    def test_schema_detection(self, sample_csv_data):
        connector = CSVConnector("test", {"file_path": sample_csv_data, "source": "local"})
        schema = connector.extract_schema()
        assert schema.total_columns == 3
