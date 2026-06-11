from core.neo4j_client import neo4j_client
import logging

logger = logging.getLogger(__name__)


class SharedAttributeAnalyzer:
    async def find_shared_director(self, din: str) -> list[dict]:
        results = await neo4j_client.run_query(
            """
            MATCH (d:Director {din: $din})-[:DIRECTED]->(c:Company)
            RETURN c.cin AS cin, c.name AS name, c.status AS status, c.riskScore AS riskScore
            ORDER BY c.riskScore DESC
            """,
            {"din": din},
        )
        return results

    async def find_shared_address(self, address: str) -> list[dict]:
        results = await neo4j_client.run_query(
            """
            MATCH (a:Address {normalizedAddress: $address})<-[:REGISTERED_AT]-(c:Company)
            RETURN c.cin AS cin, c.name AS name, c.status AS status, c.riskScore AS riskScore
            ORDER BY c.riskScore DESC
            """,
            {"address": address},
        )
        return results


shared_attribute_analyzer = SharedAttributeAnalyzer()
