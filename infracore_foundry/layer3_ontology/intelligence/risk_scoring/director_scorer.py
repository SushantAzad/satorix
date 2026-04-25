from typing import Any
import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class DirectorScorer:
    async def compute_score(self, din: str, director_props: dict[str, Any]) -> tuple[int, list[str]]:
        score = 0
        flags: list[str] = []

        disq = str(director_props.get("disqualificationStatus", "None")).strip()
        if disq.lower() == "disqualified":
            score += 50
            flags.append("DISQUALIFIED")

        if director_props.get("isOffshore"):
            score += 20
            flags.append("OFFSHORE")

        current_dirs = int(director_props.get("currentDirectorships", 0) or 0)
        if current_dirs > 15:
            score += 15
            flags.append("DIRECTOR_PROLIFERATION")

        # Check if associated with CIRP company
        try:
            cirp_result = await neo4j_client.run_query(
                """
                MATCH (d:Director {din: $din})-[:DIRECTED]->(c:Company {status: 'UnderCIRP'})
                RETURN count(c) AS cirp_count
                """,
                {"din": din},
            )
            if cirp_result and cirp_result[0].get("cirp_count", 0) > 0:
                score += 20
                flags.append("CIRP_ASSOCIATED")
        except Exception as e:
            logger.warning("Neo4j CIRP query failed for director %s: %s", din, e)

        # Check regulatory actions
        try:
            reg_result = await neo4j_client.run_query(
                """
                MATCH (d:Director {din: $din})-[:NAMED_IN]->(r:RegulatoryAction)
                RETURN count(r) AS reg_count
                """,
                {"din": din},
            )
            if reg_result and reg_result[0].get("reg_count", 0) > 0:
                score += 15
                flags.append("REGULATORY_ACTION_NAMED")
        except Exception as e:
            logger.warning("Neo4j reg query failed for director %s: %s", din, e)

        return min(score, 100), flags


director_scorer = DirectorScorer()
