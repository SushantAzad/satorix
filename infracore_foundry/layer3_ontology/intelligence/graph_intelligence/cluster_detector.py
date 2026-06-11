from core.neo4j_client import neo4j_client
import logging

logger = logging.getLogger(__name__)


class ClusterDetector:
    async def find_dense_clusters(self, min_connections: int = 3) -> list[dict]:
        results = await neo4j_client.run_query(
            """
            MATCH (c:Company)-[r:SHARES_DIRECTOR_WITH|SHARES_ADDRESS_WITH]-(other:Company)
            WITH c, count(r) AS connection_count, collect(other.name) AS connected_to
            WHERE connection_count >= $min_connections
            RETURN c.cin AS cin, c.name AS name, c.riskScore AS riskScore,
                   connection_count, connected_to
            ORDER BY connection_count DESC
            LIMIT 50
            """,
            {"min_connections": min_connections},
        )
        return results


cluster_detector = ClusterDetector()
