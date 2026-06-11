"""
ChangeDetector — identifies significant structural changes in entity networks.
Compares current graph state against a snapshot from N days ago.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


class ChangeDetector:
    async def detect_director_changes(
        self, entity_id: str, since_days: int = 90
    ) -> dict[str, Any]:
        """Directors appointed or resigned in the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[r:DIRECTED]->(c {id: $id})
                WHERE r.appointedDate >= $cutoff OR r.cessationDate >= $cutoff
                RETURN d.id AS directorId, d.name AS name,
                       r.appointedDate AS appointedDate,
                       r.cessationDate AS cessationDate,
                       r.isCurrent AS isCurrent
                """,
                id=entity_id,
                cutoff=cutoff.isoformat(),
            )
            changes = [dict(r) for r in await result.fetch(100)]

        appointments = [c for c in changes if c.get("appointedDate") and
                        _after(c["appointedDate"], cutoff)]
        resignations = [c for c in changes if c.get("cessationDate") and
                        _after(c["cessationDate"], cutoff)]

        return {
            "entity_id": entity_id,
            "since_days": since_days,
            "appointments": appointments,
            "resignations": resignations,
            "net_change": len(appointments) - len(resignations),
        }

    async def detect_ownership_changes(
        self, entity_id: str, since_days: int = 90
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (owner)-[r:OWNS]->(e {id: $id})
                WHERE r.effectiveDate >= $cutoff
                RETURN owner.id AS ownerId, labels(owner)[0] AS ownerType,
                       r.percentageHeld AS percentage, r.effectiveDate AS date
                ORDER BY r.effectiveDate DESC
                """,
                id=entity_id,
                cutoff=cutoff.isoformat(),
            )
            return [dict(r) for r in await result.fetch(100)]


def _after(date_val: Any, cutoff: datetime) -> bool:
    if not date_val:
        return False
    try:
        dt = datetime.fromisoformat(str(date_val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except (ValueError, TypeError):
        return False
