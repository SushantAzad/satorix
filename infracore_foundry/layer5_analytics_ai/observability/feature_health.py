"""Feature store health monitoring — null rates, staleness, distribution drift."""
import logging
from datetime import datetime, timezone, timedelta
from core.database import get_pool

logger = logging.getLogger(__name__)


async def get_feature_health() -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                entity_type,
                feature_name,
                count(*) AS entity_count,
                count(CASE WHEN feature_value IS NULL THEN 1 END) AS null_count,
                round(100.0 * count(CASE WHEN feature_value IS NULL THEN 1 END) / count(*), 2) AS null_rate_pct,
                max(computed_at) AS last_computed,
                avg(feature_value) AS mean_value,
                stddev(feature_value) AS std_value
            FROM l5_feature_latest,
                 jsonb_each_text(features) AS kv(feature_name, feature_value_text),
                 LATERAL (SELECT CASE WHEN kv.feature_value_text ~ '^-?[0-9]+\\.?[0-9]*$'
                                      THEN kv.feature_value_text::float ELSE NULL END AS feature_value) AS parsed
            GROUP BY entity_type, feature_name
            ORDER BY entity_type, null_rate_pct DESC
            """,
        )
        return [dict(r) for r in rows]


async def get_stale_entities(max_age_hours: int = 26) -> list[dict]:
    """Returns entities whose features haven't been recomputed within max_age_hours."""
    pool = get_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT entity_type, entity_id, computed_at FROM l5_feature_latest WHERE computed_at < $1 ORDER BY computed_at",
            cutoff,
        )
        return [dict(r) for r in rows]
