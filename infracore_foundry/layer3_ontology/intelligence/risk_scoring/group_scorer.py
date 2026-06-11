from dataclasses import dataclass
from typing import Any
import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


@dataclass
class GroupRiskAssessment:
    group_score: float
    parent_cin: str
    subsidiary_count: int
    highest_risk_entity: str
    highest_risk_score: int
    has_cirp_subsidiary: bool
    breakdown: list[dict[str, Any]]


class GroupScorer:
    async def compute_group_risk(self, parent_cin: str) -> GroupRiskAssessment:
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (parent:Company {cin: $cin})-[:OWNS*1..3]->(sub:Company)
                RETURN sub.cin AS cin, sub.name AS name, sub.riskScore AS risk, sub.status AS status
                """,
                {"cin": parent_cin},
            )
        except Exception as e:
            logger.error("Neo4j group risk query failed: %s", e)
            results = []

        # Get parent score too
        try:
            parent_result = await neo4j_client.run_query(
                "MATCH (c:Company {cin: $cin}) RETURN c.riskScore AS risk, c.name AS name, c.status AS status",
                {"cin": parent_cin},
            )
            parent_row = parent_result[0] if parent_result else {}
        except Exception:
            parent_row = {}

        all_entities = []
        if parent_row:
            all_entities.append({
                "cin": parent_cin,
                "name": parent_row.get("name", ""),
                "risk": parent_row.get("risk", 0) or 0,
                "status": parent_row.get("status", ""),
                "is_parent": True,
            })

        for row in results:
            all_entities.append({
                "cin": row.get("cin", ""),
                "name": row.get("name", ""),
                "risk": row.get("risk", 0) or 0,
                "status": row.get("status", ""),
                "is_parent": False,
            })

        if not all_entities:
            return GroupRiskAssessment(
                group_score=0.0,
                parent_cin=parent_cin,
                subsidiary_count=0,
                highest_risk_entity=parent_cin,
                highest_risk_score=0,
                has_cirp_subsidiary=False,
                breakdown=[],
            )

        has_cirp = any(e["status"] == "UnderCIRP" for e in all_entities)
        total_risk = sum(e["risk"] for e in all_entities)
        avg_risk = total_risk / len(all_entities)
        if has_cirp:
            avg_risk = min(avg_risk + 20, 100)

        highest = max(all_entities, key=lambda e: e["risk"])

        return GroupRiskAssessment(
            group_score=round(avg_risk, 2),
            parent_cin=parent_cin,
            subsidiary_count=len(results),
            highest_risk_entity=highest["name"] or highest["cin"],
            highest_risk_score=int(highest["risk"]),
            has_cirp_subsidiary=has_cirp,
            breakdown=all_entities,
        )


group_scorer = GroupScorer()
