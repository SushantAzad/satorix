import logging
from core.neo4j_client import neo4j_client
from semantic.link_types.inference import INFERENCE_RULES

logger = logging.getLogger(__name__)


class InferenceEngine:
    """Computes inferred (derived) relationships in Neo4j after each ingestion."""

    async def run_all(self) -> int:
        """Run all inference rules. Returns total inferred link count."""
        total = 0
        for rule in INFERENCE_RULES:
            try:
                count = await self._run_rule(rule)
                total += count
                logger.info("Inference rule '%s' created/updated %d links", rule.name, count)
            except Exception as e:
                logger.error("Inference rule '%s' failed: %s", rule.name, e)
        return total

    async def _run_rule(self, rule) -> int:
        results = await neo4j_client.run_write(rule.cypher_query, {})
        if results and isinstance(results, list) and results[0]:
            return results[0].get("count", 0) or results[0].get("inferred_count", 0)
        return 0

    async def infer_shares_director_with(self) -> int:
        """Explicitly infer SHARES_DIRECTOR_WITH relationships."""
        query = """
        MATCH (c1:Company)<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(c2:Company)
        WHERE c1.cin < c2.cin
        WITH c1, c2, d
        MERGE (c1)-[r:SHARES_DIRECTOR_WITH {sharedDirectorDin: d.din}]-(c2)
        ON CREATE SET r.inferredBy = 'infer_shares_director_with',
                     r.inferenceConfidence = 1.0,
                     r.sharedDirectorName = d.name,
                     r.createdAt = datetime()
        ON MATCH SET r.sharedDirectorName = d.name,
                    r.updatedAt = datetime()
        RETURN count(*) AS count
        """
        results = await neo4j_client.run_write(query, {})
        return results[0].get("count", 0) if results else 0

    async def infer_shares_address_with(self) -> int:
        query = """
        MATCH (c1:Company)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(c2:Company)
        WHERE c1.cin < c2.cin
        WITH c1, c2, a
        MERGE (c1)-[r:SHARES_ADDRESS_WITH]-(c2)
        ON CREATE SET r.inferredBy = 'infer_shares_address_with',
                     r.inferenceConfidence = 1.0,
                     r.sharedAddress = a.normalizedAddress,
                     r.createdAt = datetime()
        RETURN count(*) AS count
        """
        results = await neo4j_client.run_write(query, {})
        return results[0].get("count", 0) if results else 0

    async def infer_regulatory_contagion(self) -> int:
        query = """
        MATCH (c1:Company)-[:UNDERGOING_CIRP]->(:InsolvencyProceeding)
        MATCH (c1)-[:SHARES_DIRECTOR_WITH]-(c2:Company)
        WHERE NOT (c1)-[:REGULATORY_CONTAGION_RISK]->(c2)
        MERGE (c1)-[r:REGULATORY_CONTAGION_RISK]->(c2)
        ON CREATE SET r.riskType = 'director overlap',
                     r.severity = 'HIGH',
                     r.inferredBy = 'infer_regulatory_contagion',
                     r.inferenceConfidence = 0.9,
                     r.createdAt = datetime()
        RETURN count(*) AS count
        """
        results = await neo4j_client.run_write(query, {})
        return results[0].get("count", 0) if results else 0


inference_engine = InferenceEngine()
