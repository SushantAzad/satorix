"""
PrecursorModel — predicts CIRP (insolvency) risk using a rule-based scoring model.
Phase 1: deterministic rules (no ML training data required).
Phase 2: XGBoost trained on labeled CIRP cases (switch when 50+ examples available).

Acceptance criterion: Gujarat Highway Construction must score CRITICAL.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


@dataclass
class CIRPRiskAssessment:
    entity_id: str
    cirp_risk_score: float
    risk_band: str  # LOW | MEDIUM | HIGH | CRITICAL
    signal_breakdown: dict[str, float]
    model_version: str = "rule_v1"

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "cirp_risk_score": self.cirp_risk_score,
            "risk_band": self.risk_band,
            "signal_breakdown": self.signal_breakdown,
            "model_version": self.model_version,
        }


# Rule weights — each signal contributes these points (max 100 total)
RULE_WEIGHTS = {
    "already_under_cirp": 100.0,          # already in CIRP — trivially critical
    "high_director_turnover": 20.0,
    "rotating_directors": 15.0,
    "has_regulatory_action": 20.0,
    "has_legal_case": 15.0,
    "strike_off_risk": 10.0,
    "address_cluster_member": 10.0,
    "director_cluster_member": 10.0,
    "offshore_director": 8.0,
    "disqualified_director": 15.0,
    "high_layer3_risk_score": 20.0,
    "no_directors": 20.0,
    "no_address": 10.0,
}

BAND_THRESHOLDS = {"CRITICAL": 70, "HIGH": 45, "MEDIUM": 20, "LOW": 0}


def _risk_band(score: float) -> str:
    for band, threshold in BAND_THRESHOLDS.items():
        if score >= threshold:
            return band
    return "LOW"


class PrecursorModel:
    async def assess(self, entity_id: str) -> CIRPRiskAssessment:
        props = await self._load_entity(entity_id)
        if not props:
            return CIRPRiskAssessment(
                entity_id=entity_id,
                cirp_risk_score=0.0,
                risk_band="LOW",
                signal_breakdown={"error": "entity_not_found"},
            )

        signals: dict[str, float] = {}

        if props.get("status") == "UnderCIRP":
            signals["already_under_cirp"] = RULE_WEIGHTS["already_under_cirp"]
        elif props.get("status") == "StrikeOff":
            signals["strike_off_risk"] = RULE_WEIGHTS["strike_off_risk"]

        l3_risk = props.get("riskScore", 0) or 0
        if l3_risk >= 60:
            signals["high_layer3_risk_score"] = RULE_WEIGHTS["high_layer3_risk_score"]

        director_count = props.get("_director_count", 0)
        if director_count == 0:
            signals["no_directors"] = RULE_WEIGHTS["no_directors"]

        if not props.get("_has_address"):
            signals["no_address"] = RULE_WEIGHTS["no_address"]

        if props.get("_has_regulatory_action"):
            signals["has_regulatory_action"] = RULE_WEIGHTS["has_regulatory_action"]

        if props.get("_has_legal_case"):
            signals["has_legal_case"] = RULE_WEIGHTS["has_legal_case"]

        if props.get("_has_disqualified_director"):
            signals["disqualified_director"] = RULE_WEIGHTS["disqualified_director"]

        if props.get("_has_offshore_director"):
            signals["offshore_director"] = RULE_WEIGHTS["offshore_director"]

        if props.get("_in_address_cluster"):
            signals["address_cluster_member"] = RULE_WEIGHTS["address_cluster_member"]

        if props.get("_in_director_cluster"):
            signals["director_cluster_member"] = RULE_WEIGHTS["director_cluster_member"]

        if props.get("_high_director_turnover"):
            signals["high_director_turnover"] = RULE_WEIGHTS["high_director_turnover"]

        score = min(sum(signals.values()), 100.0)
        return CIRPRiskAssessment(
            entity_id=entity_id,
            cirp_risk_score=score,
            risk_band=_risk_band(score),
            signal_breakdown=signals,
        )

    async def batch_assess_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running CIRP precursor batch assessment")
        entity_ids = await self._load_all_company_ids()
        assessments: list[CIRPRiskAssessment] = []
        for eid in entity_ids:
            try:
                a = await self.assess(eid)
                assessments.append(a)
            except Exception as exc:
                logger.error("Precursor assessment failed for %s: %s", eid, exc)

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO l4_precursor_assessments
                    (entity_id, entity_type, cirp_risk_score, signal_breakdown,
                     risk_band, model_version, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    cirp_risk_score = EXCLUDED.cirp_risk_score,
                    signal_breakdown = EXCLUDED.signal_breakdown,
                    risk_band = EXCLUDED.risk_band,
                    computed_at = EXCLUDED.computed_at,
                    batch_run_id = EXCLUDED.batch_run_id
                """,
                [
                    (
                        a.entity_id, "Company", a.cirp_risk_score,
                        str({k: v for k, v in a.signal_breakdown.items()}),
                        a.risk_band, a.model_version,
                        datetime.now(timezone.utc), batch_run_id,
                    )
                    for a in assessments
                ],
            )

        critical = sum(1 for a in assessments if a.risk_band == "CRITICAL")
        high = sum(1 for a in assessments if a.risk_band == "HIGH")
        logger.info(
            "Precursor model: %d assessed, %d CRITICAL, %d HIGH",
            len(assessments), critical, high,
        )
        return {
            "total_assessed": len(assessments),
            "critical": critical,
            "high": high,
            "model_version": "rule_v1",
        }

    async def _load_entity(self, entity_id: str) -> dict[str, Any] | None:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c:Company {id: $id})
                OPTIONAL MATCH (d:Director)-[:DIRECTED]->(c)
                OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address)
                OPTIONAL MATCH (c)-[:HAS_REGULATORY_ACTION]->(ra:RegulatoryAction)
                OPTIONAL MATCH (c)-[:HAS_LEGAL_CASE]->(lc:LegalCase)
                WITH c,
                     count(DISTINCT d) AS dirCount,
                     count(DISTINCT a) AS addrCount,
                     count(DISTINCT ra) AS raCount,
                     count(DISTINCT lc) AS lcCount,
                     collect(DISTINCT d.isDisqualified) AS disqualFlags,
                     collect(DISTINCT d.nationality) AS nationalities
                RETURN properties(c) AS props,
                       dirCount, addrCount, raCount, lcCount,
                       disqualFlags, nationalities
                """,
                id=entity_id,
            )
            rec = await result.single()
            if not rec:
                return None

            props = dict(rec["props"])
            props["_director_count"] = rec["dirCount"]
            props["_has_address"] = rec["addrCount"] > 0
            props["_has_regulatory_action"] = rec["raCount"] > 0
            props["_has_legal_case"] = rec["lcCount"] > 0
            props["_has_disqualified_director"] = True in (rec["disqualFlags"] or [])
            props["_has_offshore_director"] = any(
                n and n.lower() not in ("indian", "india")
                for n in (rec["nationalities"] or [])
            )

            # Check cluster membership from PG
            pool = get_pool()
            async with pool.acquire() as conn:
                addr_row = await conn.fetchrow(
                    "SELECT 1 FROM l4_cluster_memberships WHERE entity_id=$1 AND cluster_type='address' LIMIT 1",
                    entity_id,
                )
                dir_row = await conn.fetchrow(
                    "SELECT 1 FROM l4_cluster_memberships WHERE entity_id=$1 AND cluster_type='director' LIMIT 1",
                    entity_id,
                )
            props["_in_address_cluster"] = addr_row is not None
            props["_in_director_cluster"] = dir_row is not None
            return props

    async def _load_all_company_ids(self) -> list[str]:
        async with get_session() as s:
            result = await s.run("MATCH (c:Company) RETURN c.id AS id")
            return [r["id"] for r in await result.fetch(100_000) if r["id"]]
