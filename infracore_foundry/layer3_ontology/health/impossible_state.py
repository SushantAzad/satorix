from typing import Any
import logging
from core.database import AsyncSessionLocal
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)


class ImpossibleStateDetector:
    async def find_violations(self) -> list[dict[str, Any]]:
        violations: list[dict] = []
        async with AsyncSessionLocal() as db:
            # 1. Operational project with no actualCompletionDate
            result = await db.execute(
                text("""
                    SELECT primary_key, properties->>'name' AS name
                    FROM ontology_objects
                    WHERE object_type = 'project'
                      AND is_deleted = FALSE
                      AND properties->>'status' = 'Operational'
                      AND (properties->>'actualCompletionDate' IS NULL
                           OR properties->>'actualCompletionDate' = '')
                """)
            )
            for row in result.fetchall():
                violations.append({
                    "object_type": "project",
                    "primary_key": row[0],
                    "name": row[1],
                    "violation": "status=Operational but actualCompletionDate is null",
                })

            # 2. paidUpCapital > authorizedCapital
            result = await db.execute(
                text("""
                    SELECT primary_key, properties->>'name' AS name,
                           (properties->>'paidUpCapital')::float AS puc,
                           (properties->>'authorizedCapital')::float AS ac
                    FROM ontology_objects
                    WHERE object_type = 'company'
                      AND is_deleted = FALSE
                      AND properties->>'paidUpCapital' IS NOT NULL
                      AND properties->>'authorizedCapital' IS NOT NULL
                      AND (properties->>'paidUpCapital')::float > (properties->>'authorizedCapital')::float
                """)
            )
            for row in result.fetchall():
                violations.append({
                    "object_type": "company",
                    "primary_key": row[0],
                    "name": row[1],
                    "violation": f"paidUpCapital ({row[2]}) > authorizedCapital ({row[3]})",
                })

        return violations


impossible_state_detector = ImpossibleStateDetector()
