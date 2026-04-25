"""Inference rule definitions for derived relationships."""
from typing import Optional


class InferenceRule:
    def __init__(
        self,
        name: str,
        link_type: str,
        description: str,
        confidence: float,
        cypher_query: str,
    ) -> None:
        self.name = name
        self.link_type = link_type
        self.description = description
        self.confidence = confidence
        self.cypher_query = cypher_query


INFERENCE_RULES = [
    InferenceRule(
        name="infer_shares_director_with",
        link_type="SHARES_DIRECTOR_WITH",
        description="Companies sharing a common active director",
        confidence=1.0,
        cypher_query="""
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
        """,
    ),
    InferenceRule(
        name="infer_shares_address_with",
        link_type="SHARES_ADDRESS_WITH",
        description="Companies sharing a registered address",
        confidence=1.0,
        cypher_query="""
        MATCH (c1:Company)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(c2:Company)
        WHERE c1.cin < c2.cin
        WITH c1, c2, a
        MERGE (c1)-[r:SHARES_ADDRESS_WITH]-(c2)
        ON CREATE SET r.inferredBy = 'infer_shares_address_with',
                     r.inferenceConfidence = 1.0,
                     r.sharedAddress = a.normalizedAddress,
                     r.createdAt = datetime()
        RETURN count(*) AS count
        """,
    ),
    InferenceRule(
        name="infer_regulatory_contagion",
        link_type="REGULATORY_CONTAGION_RISK",
        description="CIRP contagion risk through shared directors",
        confidence=0.9,
        cypher_query="""
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
        """,
    ),
    InferenceRule(
        name="infer_common_beneficial_owner",
        link_type="COMMON_BENEFICIAL_OWNER",
        description="Companies sharing an ultimate beneficial owner through ownership chains",
        confidence=0.8,
        cypher_query="""
        MATCH (target1:Company)<-[:OWNS*1..5]-(owner)
        WITH owner, collect(target1) AS targets1
        WHERE size(targets1) > 1
        UNWIND targets1 AS c1
        UNWIND targets1 AS c2
        WHERE c1.cin < c2.cin
        MERGE (c1)-[r:COMMON_BENEFICIAL_OWNER]-(c2)
        ON CREATE SET r.commonOwnerName = owner.name,
                     r.inferredBy = 'infer_common_beneficial_owner',
                     r.inferenceConfidence = 0.8,
                     r.createdAt = datetime()
        RETURN count(*) AS count
        """,
    ),
]
