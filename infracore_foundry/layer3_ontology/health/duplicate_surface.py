from typing import Any
import logging
from core.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)


class DuplicateSurface:
    async def find_candidates(self) -> list[dict[str, Any]]:
        """Find companies with duplicate_candidate flag set."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT primary_key, properties->>'name' AS name,
                           properties->>'duplicate_candidate' AS flag,
                           properties->>'similar_to' AS similar_to
                    FROM ontology_objects
                    WHERE object_type = 'company'
                      AND is_deleted = FALSE
                      AND properties->>'duplicate_candidate' = 'true'
                """)
            )
            return [
                {
                    "cin": row[0],
                    "name": row[1],
                    "similar_to": row[3],
                }
                for row in result.fetchall()
            ]


duplicate_surface = DuplicateSurface()
