"""
VelocityAnalyzer — detects anomalous rates of change.
High director turnover, rapid ownership restructuring, sudden address changes.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)

# Thresholds
HIGH_TURNOVER_THRESHOLD = 3     # directors in 180 days
RAPID_OWNERSHIP_THRESHOLD = 2   # ownership changes in 90 days


class VelocityAnalyzer:
    async def analyze(self, entity_id: str) -> dict[str, Any]:
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
        three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)

        director_velocity = await self._director_turnover(entity_id, six_months_ago)
        ownership_velocity = await self._ownership_changes(entity_id, three_months_ago)

        signals: list[str] = []
        if director_velocity["count"] >= HIGH_TURNOVER_THRESHOLD:
            signals.append(f"High director turnover: {director_velocity['count']} changes in 180 days")
        if ownership_velocity["count"] >= RAPID_OWNERSHIP_THRESHOLD:
            signals.append(f"Rapid ownership restructuring: {ownership_velocity['count']} changes in 90 days")

        return {
            "entity_id": entity_id,
            "director_velocity": director_velocity,
            "ownership_velocity": ownership_velocity,
            "velocity_signals": signals,
            "velocity_risk": "HIGH" if len(signals) >= 2 else ("MEDIUM" if signals else "LOW"),
        }

    async def _director_turnover(self, entity_id: str, since: datetime) -> dict:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[r:DIRECTED]->(c {id: $id})
                WHERE r.appointedDate >= $since OR r.cessationDate >= $since
                RETURN count(r) AS cnt
                """,
                id=entity_id, since=since.isoformat(),
            )
            rec = await result.single()
            return {"count": int(rec["cnt"]) if rec else 0, "since": since.isoformat()}

    async def _ownership_changes(self, entity_id: str, since: datetime) -> dict:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH ()-[r:OWNS]->(e {id: $id})
                WHERE r.effectiveDate >= $since
                RETURN count(r) AS cnt
                """,
                id=entity_id, since=since.isoformat(),
            )
            rec = await result.single()
            return {"count": int(rec["cnt"]) if rec else 0, "since": since.isoformat()}
