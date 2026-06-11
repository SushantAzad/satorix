from core.database import AsyncSessionLocal
from sqlalchemy import text
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TemporalAnalyzer:
    async def get_network_changes(
        self, object_type: str, object_id: str, start: datetime, end: datetime
    ) -> list[dict]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT occurred_at, event_type, property_name, old_value, new_value, actor_id
                    FROM ontology_events
                    WHERE object_type = :ot AND object_id = :oid
                      AND occurred_at BETWEEN :start AND :end
                    ORDER BY occurred_at ASC
                """),
                {"ot": object_type, "oid": object_id, "start": start, "end": end},
            )
            return [dict(row) for row in result.mappings().all()]


temporal_analyzer = TemporalAnalyzer()
