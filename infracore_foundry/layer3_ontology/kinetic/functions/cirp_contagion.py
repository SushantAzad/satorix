from dataclasses import dataclass
from typing import Any
import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


@dataclass
class ContagionRiskMap:
    source_cin: str
    affected_entities: list[dict[str, Any]]
    total_affected: int
    highest_severity: str


async def assessCIRPContagionRisk(company_cin: str) -> ContagionRiskMap:
    try:
        results = await neo4j_client.run_query(
            """
            MATCH (c:Company {cin: $cin})-[:SHARES_DIRECTOR_WITH]-(affected:Company)
            OPTIONAL MATCH path=(c)-[:SHARES_DIRECTOR_WITH]-(affected)
            RETURN affected.cin AS cin,
                   affected.name AS name,
                   affected.status AS status,
                   affected.riskScore AS riskScore
            """,
            {"cin": company_cin},
        )
    except Exception as e:
        logger.error("CIRP contagion query failed: %s", e)
        results = []

    affected = []
    for row in results:
        affected.append({
            "cin": row.get("cin"),
            "name": row.get("name"),
            "status": row.get("status"),
            "riskScore": row.get("riskScore", 0),
            "propagation_path": "SHARES_DIRECTOR_WITH",
            "severity": "HIGH",
        })

    return ContagionRiskMap(
        source_cin=company_cin,
        affected_entities=affected,
        total_affected=len(affected),
        highest_severity="HIGH" if affected else "NONE",
    )
