from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from typing import Any, Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)

# Named Cypher queries used across the system
NETWORK_EXPANSION_QUERY = """
MATCH path=(start)-[*1..$depth]-(connected)
WHERE start.cin = $cin OR start.din = $primary_key OR start.projectId = $primary_key
RETURN path, nodes(path) AS nodes, relationships(path) AS rels
LIMIT $limit
"""

BENEFICIAL_OWNERSHIP_QUERY = """
MATCH path=(c:Company {cin: $cin})<-[:OWNS*1..5]-(owner)
RETURN owner, length(path) AS depth
ORDER BY depth
"""

SHARED_DIRECTOR_QUERY = """
MATCH (c1:Company {cin: $cin})-[:DIRECTED]-(d:Director)-[:DIRECTED]-(c2:Company)
WHERE c1.cin <> c2.cin
RETURN c2, d, count(d) AS shared_director_count
"""

CIRP_CONTAGION_QUERY = """
MATCH (c1:Company {status: 'UnderCIRP'})
MATCH (c1)-[:SHARES_DIRECTOR_WITH]-(c2:Company)
RETURN c1, c2
"""

ADDRESS_CLUSTER_QUERY = """
MATCH (a:Address)<-[:REGISTERED_AT]-(c:Company)
WITH a, collect(c) AS companies, count(c) AS company_count
WHERE company_count > 5
RETURN a, companies, company_count
ORDER BY company_count DESC
"""

INFER_SHARES_DIRECTOR_QUERY = """
MATCH (c1:Company)<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(c2:Company)
WHERE c1.cin < c2.cin
WITH c1, c2, collect(d) AS shared_directors
FOREACH (d IN shared_directors |
  MERGE (c1)-[r:SHARES_DIRECTOR_WITH {sharedDirectorDin: d.din}]-(c2)
  ON CREATE SET r.inferredBy = 'infer_shares_director_with',
               r.inferenceConfidence = 1.0,
               r.sharedDirectorName = d.name,
               r.createdAt = datetime()
)
RETURN count(*) AS inferred_count
"""

INFER_SHARES_ADDRESS_QUERY = """
MATCH (c1:Company)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(c2:Company)
WHERE c1.cin < c2.cin
WITH c1, c2, a
MERGE (c1)-[r:SHARES_ADDRESS_WITH]-(c2)
ON CREATE SET r.inferredBy = 'infer_shares_address_with',
              r.inferenceConfidence = 1.0,
              r.sharedAddress = a.normalizedAddress,
              r.createdAt = datetime()
RETURN count(*) AS inferred_count
"""

INFER_REGULATORY_CONTAGION_QUERY = """
MATCH (c1:Company)-[:UNDERGOING_CIRP]->(:InsolvencyProceeding)
MATCH (c1)-[:SHARES_DIRECTOR_WITH]-(c2:Company)
WHERE NOT (c1)-[:REGULATORY_CONTAGION_RISK]->(c2)
MERGE (c1)-[r:REGULATORY_CONTAGION_RISK]->(c2)
ON CREATE SET r.riskType = 'director overlap',
              r.severity = 'HIGH',
              r.inferredBy = 'infer_regulatory_contagion',
              r.inferenceConfidence = 0.9,
              r.createdAt = datetime()
RETURN count(*) AS inferred_count
"""

SETUP_CONSTRAINTS = [
    "CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE",
    "CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE",
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.projectId IS UNIQUE",
    "CREATE CONSTRAINT reg_action_id IF NOT EXISTS FOR (r:RegulatoryAction) REQUIRE r.actionId IS UNIQUE",
    "CREATE CONSTRAINT address_key IF NOT EXISTS FOR (a:Address) REQUIRE a.normalizedAddress IS UNIQUE",
    "CREATE CONSTRAINT alert_id IF NOT EXISTS FOR (al:Alert) REQUIRE al.alertId IS UNIQUE",
    "CREATE CONSTRAINT legal_case_id IF NOT EXISTS FOR (lc:LegalCase) REQUIRE lc.caseId IS UNIQUE",
    "CREATE CONSTRAINT cirp_id IF NOT EXISTS FOR (ip:InsolvencyProceeding) REQUIRE ip.cirpId IS UNIQUE",
]

SETUP_INDEXES = [
    "CREATE INDEX company_status IF NOT EXISTS FOR (c:Company) ON (c.status)",
    "CREATE INDEX company_risk IF NOT EXISTS FOR (c:Company) ON (c.riskScore)",
    "CREATE INDEX company_state IF NOT EXISTS FOR (c:Company) ON (c.registeredState)",
    "CREATE INDEX director_offshore IF NOT EXISTS FOR (d:Director) ON (d.isOffshore)",
    "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
    "CREATE INDEX director_name IF NOT EXISTS FOR (d:Director) ON (d.name)",
]


class Neo4jClient:
    def __init__(self) -> None:
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
        )
        await self._driver.verify_connectivity()
        logger.info("Neo4j connected at %s", settings.neo4j_uri)
        await self._setup_schema()

    async def _setup_schema(self) -> None:
        async with self._driver.session() as session:
            for stmt in SETUP_CONSTRAINTS:
                try:
                    await session.run(stmt)
                except Exception as e:
                    logger.warning("Constraint setup warning: %s", e)
            for stmt in SETUP_INDEXES:
                try:
                    await session.run(stmt)
                except Exception as e:
                    logger.warning("Index setup warning: %s", e)
        logger.info("Neo4j schema constraints and indexes applied")

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j connection closed")

    def session(self) -> AsyncSession:
        if not self._driver:
            raise RuntimeError("Neo4j driver not initialized — call connect() first")
        return self._driver.session()

    async def run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        async with self.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def run_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        async with self.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            await session.commit() if hasattr(session, "commit") else None
            return records


neo4j_client = Neo4jClient()
