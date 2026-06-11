"""
Benchmarking engine — compares entity metrics against sector, scale, and peer groups.
Results persisted to l5_benchmark_results.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool
from feature_store.feature_store import list_all_entity_ids, get_latest_features

logger = logging.getLogger(__name__)


async def compute_sector_benchmarks(
    entity_type: str,
    entity_id: str,
    metric_names: list[str],
    peer_group: str = "all",
    peer_ids: Optional[list[str]] = None,
) -> dict[str, dict]:
    """
    Compute percentile rankings for the given entity across specified metrics.
    Returns {metric_name: {entity_value, sector_p25, sector_p50, sector_p75, percentile_rank}}.
    """
    if peer_ids is None:
        peer_ids = await list_all_entity_ids(entity_type)

    # Load target features
    target_feats = await get_latest_features(entity_type, entity_id)
    if target_feats is None:
        return {}

    results: dict[str, dict] = {}
    pool = get_pool()

    for metric in metric_names:
        entity_val = target_feats.get(metric)
        if entity_val is None:
            continue

        # Collect peer values
        peer_vals: list[float] = []
        for pid in peer_ids:
            if pid == entity_id:
                continue
            feats = await get_latest_features(entity_type, pid)
            if feats and feats.get(metric) is not None:
                peer_vals.append(float(feats[metric]))

        if not peer_vals:
            continue

        peer_vals_sorted = sorted(peer_vals)
        n = len(peer_vals_sorted)

        def percentile(p: float) -> float:
            idx = int(p / 100 * n)
            return peer_vals_sorted[min(idx, n - 1)]

        p25 = percentile(25)
        p50 = percentile(50)
        p75 = percentile(75)
        rank = sum(1 for v in peer_vals if v < entity_val) / n * 100

        entry = {
            "entity_value": round(float(entity_val), 4),
            "sector_p25": round(p25, 4),
            "sector_p50": round(p50, 4),
            "sector_p75": round(p75, 4),
            "percentile_rank": round(rank, 1),
        }
        results[metric] = entry

        # Persist
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO l5_benchmark_results
                        (entity_type, entity_id, metric_name, entity_value,
                         sector_p25, sector_p50, sector_p75, percentile_rank, peer_group, computed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (entity_type, entity_id, metric_name, peer_group) DO UPDATE SET
                        entity_value = EXCLUDED.entity_value,
                        sector_p25 = EXCLUDED.sector_p25,
                        sector_p50 = EXCLUDED.sector_p50,
                        sector_p75 = EXCLUDED.sector_p75,
                        percentile_rank = EXCLUDED.percentile_rank,
                        computed_at = EXCLUDED.computed_at
                    """,
                    entity_type, entity_id, metric, float(entity_val),
                    p25, p50, p75, rank, peer_group, datetime.now(timezone.utc),
                )
        except Exception as exc:
            logger.warning("Benchmark store failed for %s/%s/%s: %s", entity_type, entity_id, metric, exc)

    return results


async def get_benchmarks(entity_type: str, entity_id: str) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT metric_name, entity_value, sector_p25, sector_p50, sector_p75,
                   percentile_rank, peer_group, computed_at
            FROM l5_benchmark_results
            WHERE entity_type=$1 AND entity_id=$2
            ORDER BY metric_name
            """,
            entity_type, entity_id,
        )
        return [dict(r) for r in rows]
