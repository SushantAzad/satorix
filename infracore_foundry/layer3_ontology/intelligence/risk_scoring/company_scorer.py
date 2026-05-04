from dataclasses import dataclass, field
from typing import Any
import logging
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


@dataclass
class RiskScoreResult:
    score: int
    flags: list[str] = field(default_factory=list)
    confidence: str = "MEDIUM"


class CompanyScorer:
    async def compute_score(self, company_cin: str, company_props: dict[str, Any]) -> tuple[int, list[str]]:
        """Returns (risk_score 0-100, risk_flags list)."""
        score = 0
        flags: list[str] = []

        status = str(company_props.get("status", "")).strip()
        if status == "UnderCIRP":
            score += 30
            flags.append("CIRP_ACTIVE")
        elif status == "StrikeOff":
            score += 15
            flags.append("STRUCK_OFF")

        # Regulatory actions from Neo4j
        try:
            reg_results = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})-[:SUBJECT_OF]->(r:RegulatoryAction)
                RETURN r.status AS status
                """,
                {"cin": company_cin},
            )
            ongoing = sum(1 for r in reg_results if str(r.get("status", "")).lower() == "ongoing")
            resolved = sum(1 for r in reg_results if str(r.get("status", "")).lower() == "resolved")
            score += min(ongoing * 20, 40)
            score += min(resolved * 8, 16)
            if ongoing > 0:
                flags.append("ONGOING_REGULATORY")
        except Exception as e:
            logger.warning("Neo4j regulatory query failed for %s: %s", company_cin, e)

        # Director flags
        try:
            dir_results = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})<-[:DIRECTED]-(d:Director)
                WHERE d.isCurrent IS NULL OR d.isCurrent <> false
                RETURN d.isOffshore AS offshore, d.disqualificationStatus AS disq
                """,
                {"cin": company_cin},
            )
            has_offshore = any(r.get("offshore") for r in dir_results)
            has_disqualified = any(
                str(r.get("disq", "")).lower() == "disqualified" for r in dir_results
            )
            if has_offshore:
                score += 15
                flags.append("OFFSHORE_DIRECTOR")
            if has_disqualified:
                score += 20
                flags.append("DISQUALIFIED_DIRECTOR")
        except Exception as e:
            logger.warning("Neo4j director query failed for %s: %s", company_cin, e)

        # Project stress
        try:
            proj_results = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})-[:OWNS_PROJECT]->(p:Project)
                RETURN p.status AS status
                """,
                {"cin": company_cin},
            )
            for proj in proj_results:
                ps = str(proj.get("status", ""))
                if ps == "Stressed":
                    score += 25
                    flags.append("STRESSED_PROJECT")
                elif ps == "Under Construction":
                    score += 10
        except Exception as e:
            logger.warning("Neo4j project query failed for %s: %s", company_cin, e)

        # Address clustering
        try:
            addr_result = await neo4j_client.run_query(
                """
                MATCH (c:Company {cin: $cin})-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(other:Company)
                RETURN count(DISTINCT other) AS shared_count
                """,
                {"cin": company_cin},
            )
            if addr_result and addr_result[0].get("shared_count", 0) > 5:
                score += 10
                flags.append("ADDRESS_CLUSTERING")
        except Exception as e:
            logger.warning("Neo4j address query failed for %s: %s", company_cin, e)

        return min(score, 100), flags


    def score(self, company_props: dict[str, Any]) -> RiskScoreResult:
        """Synchronous heuristic scorer using props only (no DB). Used for testing and fast-path scoring."""
        s = 0
        flags: list[str] = []
        status = str(company_props.get("status", "")).strip()
        if "CIRP" in status or "Insolvency" in status or "UnderCIRP" in status:
            s += 30
            flags.append("CIRP_ACTIVE")
        elif status in ("StrikeOff", "Struck Off"):
            s += 15
            flags.append("STRUCK_OFF")
        for f in company_props.get("riskFlags", []):
            if f not in flags:
                flags.append(f)
                s += 10
        delay = int(company_props.get("delayMonths", 0) or 0)
        if delay > 0:
            s += min(delay // 6 * 5, 20)
        s = min(s, 100)
        confidence = "HIGH" if len(flags) >= 2 else ("MEDIUM" if len(flags) == 1 else "LOW")
        return RiskScoreResult(score=s, flags=flags, confidence=confidence)


company_scorer = CompanyScorer()
CompanyRiskScorer = CompanyScorer
