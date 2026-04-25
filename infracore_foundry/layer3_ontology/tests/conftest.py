import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_neo4j():
    with patch("core.neo4j_client.neo4j_client") as mock:
        mock.run_query = AsyncMock(return_value=[])
        mock.run_write = AsyncMock(return_value=[{"count": 0}])
        yield mock


@pytest.fixture
def mock_redis():
    with patch("core.redis_client.redis_client") as mock:
        mock.get_object = AsyncMock(return_value=None)
        mock.set_object = AsyncMock()
        mock.invalidate_object = AsyncMock()
        yield mock


@pytest.fixture
def mock_es():
    with patch("core.elasticsearch_client.es_client") as mock:
        mock.index_document = AsyncMock()
        mock.search = AsyncMock(return_value=[])
        yield mock


@pytest.fixture
def sample_company_data():
    return {
        "cin": "L45201MH2003PLC142301",
        "name": "Infracore Developments Limited",
        "status": "Active",
        "registeredState": "Maharashtra",
        "companyType": "Public Limited",
        "authorizedCapital": 5000000000.0,
        "paidUpCapital": 2500000000.0,
        "riskScore": 45,
    }


@pytest.fixture
def sample_director_data():
    return {
        "din": "00112233",
        "name": "Arvind Kapoor",
        "nationality": "Indian",
        "disqualificationStatus": "None",
        "currentDirectorships": 8,
        "isOffshore": False,
    }
