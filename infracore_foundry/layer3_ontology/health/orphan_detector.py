import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class OrphanDetector:
    async def find_orphans(self) -> list[dict]:
        """Find nodes with zero relationships in Neo4j."""
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (n)
                WHERE NOT (n)--()
                RETURN labels(n)[0] AS object_type,
                       CASE labels(n)[0]
                         WHEN 'Company' THEN n.cin
                         WHEN 'Director' THEN n.din
                         WHEN 'Project' THEN n.projectId
                         ELSE coalesce(n.id, toString(id(n)))
                       END AS primary_key,
                       properties(n) AS props
                LIMIT 100
                """
            )
        except Exception as e:
            logger.error("Orphan detection query failed: %s", e)
            return []

        return [
            {
                "object_type": r.get("object_type"),
                "primary_key": r.get("primary_key"),
                "name": (r.get("props") or {}).get("name", ""),
            }
            for r in results
        ]


orphan_detector = OrphanDetector()
