"""
Model observability — prediction volume, latency, score distribution, and drift monitoring.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.database import get_pool

logger = logging.getLogger(__name__)


async def get_model_health_summary() -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                m.model_name,
                m.version,
                m.status,
                m.evaluation_metrics,
                m.training_date,
                count(p.id) AS prediction_count_7d,
                avg(p.prediction_value) AS avg_prediction_7d,
                stddev(p.prediction_value) AS std_prediction_7d
            FROM l5_models m
            LEFT JOIN l5_predictions p
                ON p.model_id = m.model_id
                AND p.predicted_at > NOW() - INTERVAL '7 days'
            WHERE m.status IN ('champion', 'challenger')
            GROUP BY m.model_id, m.model_name, m.version, m.status,
                     m.evaluation_metrics, m.training_date
            ORDER BY m.model_name, m.training_date DESC
            """,
        )
        return [dict(r) for r in rows]


async def get_prediction_distribution(model_name: str, days: int = 7) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.prediction_value
            FROM l5_predictions p
            JOIN l5_models m ON m.model_id = p.model_id
            WHERE m.model_name=$1
              AND m.status='champion'
              AND p.predicted_at > NOW() - ($2 * INTERVAL '1 day')
            """,
            model_name, days,
        )
        vals = [float(r["prediction_value"]) for r in rows if r["prediction_value"] is not None]
        if not vals:
            return {"model_name": model_name, "count": 0}

        buckets = [0] * 10
        for v in vals:
            idx = min(int(v * 10), 9)
            buckets[idx] += 1

        return {
            "model_name": model_name,
            "count": len(vals),
            "mean": round(sum(vals) / len(vals), 4),
            "distribution": {f"{i*10}-{(i+1)*10}%": buckets[i] for i in range(10)},
        }
