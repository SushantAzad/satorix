"""
Time-series trend detection for numeric properties on ontology entities.
Computes direction, velocity, inflection points, and anomaly scores.
Results persisted to l5_trend_results.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool

logger = logging.getLogger(__name__)


def _linear_slope(values: list[float]) -> float:
    """Returns slope of linear fit through (index, value) pairs."""
    if len(values) < 2:
        return 0.0
    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator > 0 else 0.0


def detect_trend(values: list[float]) -> dict:
    """
    Analyse a time-ordered list of numeric values.
    Returns: direction, velocity, has_inflection, anomaly_score.
    """
    if not values:
        return {"direction": "stable", "velocity": 0.0, "has_inflection": False, "anomaly_score": 0.0}

    slope = _linear_slope(values)
    std = (sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)) ** 0.5
    mean_abs = abs(sum(values) / len(values)) or 1.0
    normalised_slope = slope / mean_abs

    if abs(normalised_slope) < 0.02:
        direction = "stable"
    elif normalised_slope > 0:
        direction = "rising"
    else:
        direction = "falling"

    # Inflection: first half slope vs second half slope have opposite signs
    mid = len(values) // 2
    first_slope = _linear_slope(values[:mid]) if mid >= 2 else slope
    second_slope = _linear_slope(values[mid:]) if len(values) - mid >= 2 else slope
    has_inflection = (first_slope * second_slope < 0) and abs(first_slope - second_slope) > std * 0.5

    # Anomaly: last value more than 2σ from mean
    mean = sum(values) / len(values)
    anomaly_score = abs(values[-1] - mean) / (std or 1.0) if std > 0 else 0.0

    return {
        "direction": "inflecting" if has_inflection else direction,
        "velocity": round(normalised_slope, 5),
        "has_inflection": has_inflection,
        "anomaly_score": round(min(anomaly_score, 10.0), 3),
    }


async def compute_and_store_trend(
    entity_type: str,
    entity_id: str,
    metric_name: str,
    values: list[float],
) -> dict:
    result = detect_trend(values)
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO l5_trend_results
                    (entity_type, entity_id, metric_name, direction, velocity,
                     has_inflection, anomaly_score, data_points, computed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                ON CONFLICT (entity_type, entity_id, metric_name) DO UPDATE SET
                    direction = EXCLUDED.direction,
                    velocity = EXCLUDED.velocity,
                    has_inflection = EXCLUDED.has_inflection,
                    anomaly_score = EXCLUDED.anomaly_score,
                    data_points = EXCLUDED.data_points,
                    computed_at = EXCLUDED.computed_at
                """,
                entity_type, entity_id, metric_name,
                result["direction"], result["velocity"],
                result["has_inflection"], result["anomaly_score"],
                json.dumps(values), datetime.now(timezone.utc),
            )
    except Exception as exc:
        logger.warning("Trend store failed for %s/%s/%s: %s", entity_type, entity_id, metric_name, exc)
    return result


async def get_trend(entity_type: str, entity_id: str, metric_name: str) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT direction, velocity, has_inflection, anomaly_score, data_points, computed_at
            FROM l5_trend_results
            WHERE entity_type=$1 AND entity_id=$2 AND metric_name=$3
            """,
            entity_type, entity_id, metric_name,
        )
        if not row:
            return None
        return {
            "direction": row["direction"],
            "velocity": row["velocity"],
            "has_inflection": row["has_inflection"],
            "anomaly_score": row["anomaly_score"],
            "data_points": row["data_points"] if isinstance(row["data_points"], list) else json.loads(row["data_points"] or "[]"),
            "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
        }
