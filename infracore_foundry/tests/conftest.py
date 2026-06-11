"""Pytest configuration and shared fixtures."""

import os
import sys
from unittest.mock import MagicMock

import pytest
import pandas as pd

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def sample_company_df():
    """Sample Indian company data."""
    return pd.DataFrame({
        "CIN": ["U72200MH2009PTC194000", "L17110MH1973PLC019786", "U72200KA2004PTC033636"],
        "CompanyName": ["TATA CONSULTANCY SERVICES", "RELIANCE INDUSTRIES", "INFOSYS LTD"],
        "Status": ["Active", "Active", "Active"],
        "PaidUpCapital": [500000000, 1000000000, 300000000],
        "AuthorizedCapital": [1000000000, 2000000000, 500000000],
        "IncorporationDate": ["2009-01-15", "1973-09-12", "2004-07-04"],
        "RegisteredState": ["Maharashtra", "Maharashtra", "Karnataka"],
    })


@pytest.fixture
def sample_gstin_df():
    """Sample GSTIN data."""
    return pd.DataFrame({
        "GSTIN": ["27AABCU9603R1ZM", "29AABCU9603R1ZM"],
        "BusinessName": ["Test Business 1", "Test Business 2"],
        "StateCode": ["27", "29"],
    })


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.first.return_value = None
    session.all.return_value = []
    return session


@pytest.fixture
def empty_df():
    """Empty DataFrame."""
    return pd.DataFrame()


@pytest.fixture
def sample_csv_data(tmp_path):
    """Create a sample CSV file for testing."""
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [30, 25, 35],
        "city": ["Mumbai", "Delhi", "Bangalore"],
    })
    df.to_csv(csv_path, index=False)
    return str(csv_path)
