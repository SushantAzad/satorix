"""
Cross-entity correlation discovery.
Finds non-obvious correlations between feature pairs across the full entity population.
High-confidence correlations are candidates for new ML features or L3 anomaly rules.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool
from feature_store.feature_store import list_all_entity_ids, get_latest_features
from feature_store.feature_registry import get_feature_names

logger = logging.getLogger(__name__)

MIN_SAMPLE_SIZE = 30
P_VALUE_THRESHOLD = 0.05


async def discover_correlations(entity_type: str = "Company") -> list[dict]:
    """
    Compute Pearson correlation coefficient for all feature pairs.
    Persists statistically significant results to l5_correlations.
    Returns list of significant correlations.
    """
    feature_names = get_feature_names(entity_type)
    entity_ids = await list_all_entity_ids(entity_type)

    if len(entity_ids) < MIN_SAMPLE_SIZE:
        logger.info("Insufficient entities for correlation analysis (%d < %d)", len(entity_ids), MIN_SAMPLE_SIZE)
        return []

    # Build feature matrix
    rows: list[dict] = []
    for eid in entity_ids:
        feats = await get_latest_features(entity_type, eid)
        if feats:
            rows.append(feats)

    if len(rows) < MIN_SAMPLE_SIZE:
        return []

    try:
        import numpy as np
        from scipy import stats

        data = np.array(
            [[r.get(f, 0.0) or 0.0 for f in feature_names] for r in rows],
            dtype=float,
        )

        significant: list[dict] = []
        pool = get_pool()
        n = len(feature_names)

        for i in range(n):
            for j in range(i + 1, n):
                col_a = data[:, i]
                col_b = data[:, j]
                # Skip constant columns
                if col_a.std() == 0 or col_b.std() == 0:
                    continue
                corr, p_val = stats.pearsonr(col_a, col_b)
                if abs(corr) >= 0.30 and p_val <= P_VALUE_THRESHOLD:
                    entry = {
                        "feature_a": feature_names[i],
                        "feature_b": feature_names[j],
                        "correlation_coefficient": round(float(corr), 4),
                        "p_value": round(float(p_val), 6),
                        "sample_size": len(rows),
                        "entity_type": entity_type,
                    }
                    significant.append(entry)
                    try:
                        async with pool.acquire() as conn:
                            await conn.execute(
                                """
                                INSERT INTO l5_correlations
                                    (feature_a, feature_b, correlation_coefficient, p_value,
                                     sample_size, entity_type, computed_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (feature_a, feature_b, lag_periods, entity_type) DO UPDATE SET
                                    correlation_coefficient = EXCLUDED.correlation_coefficient,
                                    p_value = EXCLUDED.p_value,
                                    sample_size = EXCLUDED.sample_size,
                                    computed_at = EXCLUDED.computed_at
                                """,
                                feature_names[i], feature_names[j],
                                float(corr), float(p_val),
                                len(rows), entity_type,
                                datetime.now(timezone.utc),
                            )
                    except Exception as exc:
                        logger.warning("Correlation store failed: %s", exc)

        logger.info("Correlation discovery: %d significant pairs found for %s", len(significant), entity_type)
        return significant

    except ImportError:
        logger.warning("scipy not installed — correlation discovery skipped")
        return []


async def get_top_correlations(entity_type: str = "Company", min_abs_corr: float = 0.40) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT feature_a, feature_b, correlation_coefficient, p_value, sample_size, computed_at
            FROM l5_correlations
            WHERE entity_type=$1 AND abs(correlation_coefficient) >= $2
            ORDER BY abs(correlation_coefficient) DESC LIMIT 50
            """,
            entity_type, min_abs_corr,
        )
        return [dict(r) for r in rows]
