import pytest
import pytest_asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_company_scorer_cirp_adds_30():
    with patch("core.neo4j_client.neo4j_client") as mock_neo4j:
        mock_neo4j.run_query = AsyncMock(return_value=[])
        from intelligence.risk_scoring.company_scorer import CompanyScorer
        scorer = CompanyScorer()
        score, flags = await scorer.compute_score("L45201MH2003PLC142301", {"status": "UnderCIRP"})
        assert score >= 30
        assert "CIRP_ACTIVE" in flags


@pytest.mark.asyncio
async def test_company_scorer_capped_at_100():
    with patch("core.neo4j_client.neo4j_client") as mock_neo4j:
        mock_neo4j.run_query = AsyncMock(return_value=[
            {"status": "ongoing"},
            {"status": "ongoing"},
            {"status": "ongoing"},
        ])
        from intelligence.risk_scoring.company_scorer import CompanyScorer
        scorer = CompanyScorer()
        score, flags = await scorer.compute_score(
            "L45201MH2003PLC142301",
            {"status": "UnderCIRP"},
        )
        assert score <= 100


@pytest.mark.asyncio
async def test_director_scorer_disqualified():
    with patch("core.neo4j_client.neo4j_client") as mock_neo4j:
        mock_neo4j.run_query = AsyncMock(return_value=[{"cirp_count": 0}, {"reg_count": 0}])
        from intelligence.risk_scoring.director_scorer import DirectorScorer
        scorer = DirectorScorer()
        score, flags = await scorer.compute_score("00112233", {"disqualificationStatus": "Disqualified"})
        assert score >= 50
        assert "DISQUALIFIED" in flags


@pytest.mark.asyncio
async def test_project_scorer_stressed():
    from intelligence.risk_scoring.project_scorer import ProjectScorer
    scorer = ProjectScorer()
    score, flags = await scorer.compute_score("PRJ001", {"status": "Stressed", "delayMonths": 30, "costOverrunPercent": 25})
    assert score >= 40
    assert "PROJECT_STRESSED" in flags
    assert "SEVERE_DELAY" in flags
    assert "COST_OVERRUN" in flags


@pytest.mark.asyncio
async def test_project_probability_no_risk():
    with patch("core.neo4j_client.neo4j_client") as mock_neo4j:
        mock_neo4j.run_query = AsyncMock(return_value=[{"rs": 20}])
        with patch("core.database.AsyncSessionLocal") as mock_session:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.first = MagicMock(return_value=[{"status": "Under Construction", "delayMonths": 0}])
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value = mock_db

            from kinetic.functions.project_probability import predictProjectCompletionProbability
            forecast = await predictProjectCompletionProbability("PRJ001")
            assert 0 <= forecast.probability <= 1
