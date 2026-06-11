"""
ModelRegistry — CRUD for l5_models table.
Tracks champion/challenger lifecycle.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from core.database import get_pool
from core.config import settings

logger = logging.getLogger(__name__)


class ModelRegistry:

    async def register(
        self,
        model_name: str,
        model_type: str,
        version: str,
        evaluation_metrics: dict,
        artifact_path: Optional[str] = None,
        hyperparameters: Optional[dict] = None,
        training_sample_size: Optional[int] = None,
        status: str = "challenger",
    ) -> str:
        """Register a new model version. Returns model_id."""
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO l5_models
                    (model_name, model_type, version, status, training_date,
                     feature_schema_version, evaluation_metrics, model_artifact_path,
                     hyperparameters, training_sample_size)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::jsonb, $10)
                ON CONFLICT (model_name, version) DO UPDATE SET
                    status = EXCLUDED.status,
                    evaluation_metrics = EXCLUDED.evaluation_metrics,
                    model_artifact_path = EXCLUDED.model_artifact_path,
                    training_date = EXCLUDED.training_date
                RETURNING model_id
                """,
                model_name, model_type, version, status,
                datetime.now(timezone.utc),
                settings.feature_schema_version,
                json.dumps(evaluation_metrics),
                artifact_path,
                json.dumps(hyperparameters or {}),
                training_sample_size,
            )
            model_id = str(row["model_id"])
            logger.info("Registered model %s v%s id=%s status=%s", model_name, version, model_id, status)
            return model_id

    async def get_champion(self, model_name: str) -> Optional[dict]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM l5_models WHERE model_name=$1 AND status='champion' ORDER BY training_date DESC LIMIT 1",
                model_name,
            )
            return dict(row) if row else None

    async def promote_to_champion(self, model_id: str, model_name: str) -> None:
        """Demote current champion to 'retired', promote new challenger."""
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE l5_models SET status='retired' WHERE model_name=$1 AND status='champion'",
                    model_name,
                )
                await conn.execute(
                    "UPDATE l5_models SET status='champion' WHERE model_id=$1",
                    uuid.UUID(model_id),
                )
        logger.info("Promoted model %s to champion for %s", model_id, model_name)

    async def list_models(self, model_name: Optional[str] = None) -> list[dict]:
        pool = get_pool()
        async with pool.acquire() as conn:
            if model_name:
                rows = await conn.fetch(
                    "SELECT * FROM l5_models WHERE model_name=$1 ORDER BY training_date DESC",
                    model_name,
                )
            else:
                rows = await conn.fetch("SELECT * FROM l5_models ORDER BY training_date DESC LIMIT 100")
            return [dict(r) for r in rows]


model_registry = ModelRegistry()
