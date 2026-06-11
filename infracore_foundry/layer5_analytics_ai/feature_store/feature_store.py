"""
CRUD layer for l5_feature_store and l5_feature_latest.
Provides get_latest_features() used by model serving and training.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool
from core.config import settings

logger = logging.getLogger(__name__)


async def upsert_features(entity_type: str, entity_id: str, features: dict[str, float]) -> None:
    """Write a full feature vector snapshot to both l5_feature_store and l5_feature_latest."""
    pool = get_pool()
    now = datetime.now(timezone.utc)
    sv = settings.feature_schema_version

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Insert point-in-time record
            await conn.executemany(
                """
                INSERT INTO l5_feature_store
                    (entity_type, entity_id, feature_name, feature_value, computed_at, schema_version)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (entity_type, entity_id, feature_name, computed_at) DO NOTHING
                """,
                [
                    (entity_type, entity_id, name, value, now, sv)
                    for name, value in features.items()
                    if value is not None
                ],
            )
            # Upsert latest snapshot
            await conn.execute(
                """
                INSERT INTO l5_feature_latest (entity_type, entity_id, features, schema_version, computed_at)
                VALUES ($1, $2, $3::jsonb, $4, $5)
                ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                    features = EXCLUDED.features,
                    schema_version = EXCLUDED.schema_version,
                    computed_at = EXCLUDED.computed_at
                """,
                entity_type, entity_id, json.dumps(features), sv, now,
            )


async def get_latest_features(entity_type: str, entity_id: str) -> Optional[dict[str, float]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT features, schema_version FROM l5_feature_latest WHERE entity_type=$1 AND entity_id=$2",
            entity_type, entity_id,
        )
        if not row:
            return None
        feats = row["features"] if isinstance(row["features"], dict) else json.loads(row["features"] or "{}")
        return feats


async def get_features_at_time(
    entity_type: str,
    entity_id: str,
    as_of: datetime,
) -> Optional[dict[str, float]]:
    """Return the feature vector closest to `as_of` for historical training."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT feature_name, feature_value
            FROM l5_feature_store
            WHERE entity_type=$1 AND entity_id=$2 AND computed_at <= $3
            ORDER BY computed_at DESC
            LIMIT 100
            """,
            entity_type, entity_id, as_of,
        )
        if not rows:
            return None
        # Each row is the latest value for that feature as of `as_of`
        seen: dict[str, float] = {}
        for row in rows:
            name = row["feature_name"]
            if name not in seen and row["feature_value"] is not None:
                seen[name] = float(row["feature_value"])
        return seen if seen else None


async def list_all_entity_ids(entity_type: str) -> list[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT entity_id FROM l5_feature_latest WHERE entity_type=$1",
            entity_type,
        )
        return [r["entity_id"] for r in rows]
