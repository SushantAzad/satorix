import logging
from core.config import settings
from core.database import AsyncSessionLocal
from storage.object_data_funnel import object_data_funnel
from sqlalchemy import text
from .company_scorer import company_scorer
from .director_scorer import director_scorer
from .project_scorer import project_scorer

logger = logging.getLogger(__name__)


class RiskScoringEngine:
    async def score_all(self) -> int:
        """Recompute risk scores for all objects. Returns count of updated scores."""
        updated = 0
        updated += await self._score_companies()
        updated += await self._score_directors()
        updated += await self._score_projects()
        logger.info("Risk scoring complete: %d scores updated", updated)
        return updated

    async def score_company(self, cin: str, props: dict) -> tuple[int, list[str]]:
        return await company_scorer.compute_score(cin, props)

    async def score_director(self, din: str, props: dict) -> tuple[int, list[str]]:
        return await director_scorer.compute_score(din, props)

    async def score_project(self, project_id: str, props: dict) -> tuple[int, list[str]]:
        return await project_scorer.compute_score(project_id, props)

    async def _score_companies(self) -> int:
        count = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT primary_key, properties FROM ontology_objects WHERE object_type = 'company' AND is_deleted = FALSE")
            )
            rows = result.fetchall()

        batch_size = settings.risk_score_batch_size
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            for row in batch:
                cin = row[0]
                import json
                props = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
                try:
                    score, flags = await company_scorer.compute_score(cin, props)
                    result = await object_data_funnel.write_object(
                        object_type="company",
                        data={**props, "riskScore": score, "riskFlags": flags},
                        source="risk_scoring_engine",
                        actor="system",
                    )
                    if result.success:
                        count += 1
                except Exception as e:
                    logger.error("Company scoring failed for %s: %s", cin, e)
        return count

    async def _score_directors(self) -> int:
        count = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT primary_key, properties FROM ontology_objects WHERE object_type = 'director' AND is_deleted = FALSE")
            )
            rows = result.fetchall()

        for row in rows:
            din = row[0]
            import json
            props = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            try:
                score, flags = await director_scorer.compute_score(din, props)
                await object_data_funnel.write_object(
                    object_type="director",
                    data={**props, "riskScore": score, "riskFlags": flags},
                    source="risk_scoring_engine",
                    actor="system",
                )
                count += 1
            except Exception as e:
                logger.error("Director scoring failed for %s: %s", din, e)
        return count

    async def _score_projects(self) -> int:
        count = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT primary_key, properties FROM ontology_objects WHERE object_type = 'project' AND is_deleted = FALSE")
            )
            rows = result.fetchall()

        for row in rows:
            pid = row[0]
            import json
            props = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            try:
                score, flags = await project_scorer.compute_score(pid, props)
                await object_data_funnel.write_object(
                    object_type="project",
                    data={**props, "riskScore": score, "riskFlags": flags},
                    source="risk_scoring_engine",
                    actor="system",
                )
                count += 1
            except Exception as e:
                logger.error("Project scoring failed for %s: %s", pid, e)
        return count


risk_scoring_engine = RiskScoringEngine()
