"""Trend, benchmark, and correlation analytics endpoints."""
from fastapi import APIRouter, Query
from typing import Optional

from analytics.trend_detector import get_trend, compute_and_store_trend
from analytics.benchmarking import get_benchmarks, compute_sector_benchmarks
from analytics.correlation import get_top_correlations

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/trends/{entity_type}/{entity_id}")
async def get_entity_trends(entity_type: str, entity_id: str):
    from core.database import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT metric_name, direction, velocity, has_inflection, anomaly_score, computed_at FROM l5_trend_results WHERE entity_type=$1 AND entity_id=$2",
            entity_type, entity_id,
        )
    return {"entity_type": entity_type, "entity_id": entity_id, "trends": [dict(r) for r in rows]}


@router.get("/trends/{entity_type}/{entity_id}/{metric}")
async def get_single_trend(entity_type: str, entity_id: str, metric: str):
    trend = await get_trend(entity_type, entity_id, metric)
    if not trend:
        return {"entity_id": entity_id, "metric": metric, "status": "no_data"}
    return {"entity_id": entity_id, "metric": metric, **trend}


@router.get("/benchmarks/{entity_type}/{entity_id}")
async def get_entity_benchmarks(entity_type: str, entity_id: str):
    benchmarks = await get_benchmarks(entity_type, entity_id)
    return {"entity_id": entity_id, "benchmarks": benchmarks}


@router.post("/benchmarks/{entity_type}/{entity_id}/compute")
async def compute_benchmarks(entity_type: str, entity_id: str, metrics: list[str] = Query(default=[])):
    if not metrics:
        metrics = ["layer3_risk_score", "current_ratio", "debt_equity_ratio", "avg_project_delay_months"]
    results = await compute_sector_benchmarks(entity_type, entity_id, metrics)
    return {"entity_id": entity_id, "benchmarks": results}


@router.get("/correlations")
async def get_correlations(entity_type: str = "Company", min_correlation: float = 0.40):
    correlations = await get_top_correlations(entity_type, min_correlation)
    return {"entity_type": entity_type, "correlations": correlations}
