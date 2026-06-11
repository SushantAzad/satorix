"""
NegativeSpace — detects what connections are absent but expected.
Useful for identifying shell companies (many directors, no address links)
or regulatory blind-spots (company with no RegulatoryBody filings).
"""
import logging
from dataclasses import dataclass

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


@dataclass
class AbsenceSignal:
    entity_id: str
    entity_type: str
    expected_relationship: str
    reason: str
    severity: str  # LOW | MEDIUM | HIGH


class NegativeSpaceAnalyzer:
    EXPECTED_RELS = {
        "Company": [
            ("REGISTERED_AT", "Company should have a registered address"),
            ("DIRECTED", "Company should have at least one director"),
        ],
        "Director": [
            ("DIRECTED", "Director should be linked to at least one company"),
        ],
    }

    async def analyze(self, entity_id: str, entity_type: str) -> list[AbsenceSignal]:
        signals: list[AbsenceSignal] = []
        expected = self.EXPECTED_RELS.get(entity_type, [])
        if not expected:
            return signals

        async with get_session() as s:
            result = await s.run(
                """
                MATCH (e {id: $id})
                OPTIONAL MATCH (e)-[r]-()
                RETURN collect(distinct type(r)) AS relTypes
                """,
                id=entity_id,
            )
            rec = await result.single()
            existing_rels = set(rec["relTypes"] if rec else [])

        for rel_type, reason in expected:
            if rel_type not in existing_rels:
                signals.append(AbsenceSignal(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    expected_relationship=rel_type,
                    reason=reason,
                    severity="HIGH" if rel_type == "DIRECTED" else "MEDIUM",
                ))
        return signals
