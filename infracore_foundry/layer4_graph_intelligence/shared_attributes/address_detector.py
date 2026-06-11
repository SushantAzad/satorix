"""
SharedAddressDetector — identifies pairs of companies sharing a registered address.
Results feed back through the ObjectDataFunnel as SHARES_ADDRESS_WITH links.
"""
import logging
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


class SharedAddressDetector:
    async def detect(self, entity_id: str) -> list[dict[str, Any]]:
        """Return companies sharing any registered address with entity_id."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c {id: $id})-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(other)
                WHERE other.id <> $id
                RETURN other.id AS entityId, labels(other)[0] AS entityType,
                       a.id AS sharedAddressId, a.address AS sharedAddress,
                       other.name AS entityName
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(100)]

    async def detect_bulk(self, limit: int = 10000) -> list[dict[str, Any]]:
        """Return all shared-address pairs across the full graph."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (a:Address)<-[:REGISTERED_AT]-(c1)
                MATCH (a)<-[:REGISTERED_AT]-(c2)
                WHERE id(c1) < id(c2)
                RETURN c1.id AS entity1, labels(c1)[0] AS type1,
                       c2.id AS entity2, labels(c2)[0] AS type2,
                       a.id AS addressId, a.address AS address
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in await result.fetch(limit)]


AddressConnectionDetector = SharedAddressDetector
