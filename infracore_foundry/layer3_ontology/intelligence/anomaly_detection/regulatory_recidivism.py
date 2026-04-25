import logging
from datetime import datetime, timezone
from storage.object_data_funnel import object_data_funnel
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class RegulatoryRecidivismDetector:
    async def detect(self) -> int:
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (c:Company)-[:SUBJECT_OF]->(r:RegulatoryAction)
                WITH c, collect(DISTINCT r.issuingBody) AS bodies, count(DISTINCT r.issuingBody) AS body_count
                WHERE body_count >= 3
                RETURN c.cin AS cin, c.name AS name, body_count, bodies
                """
            )
        except Exception as e:
            logger.error("Regulatory recidivism query failed: %s", e)
            return 0

        alert_count = 0
        for row in results:
            cin = row.get("cin", "")
            name = row.get("name", "")
            count = row.get("body_count", 0)
            bodies = row.get("bodies", [])

            alert_id = f"RECRV-{cin}"
            result = await object_data_funnel.write_object(
                object_type="alert",
                data={
                    "alertId": alert_id,
                    "severity": "CRITICAL",
                    "alertType": "REGULATORY_RECIDIVISM",
                    "title": f"Regulatory Recidivism: {name}",
                    "message": f"Company {name} (CIN: {cin}) has regulatory actions from {count} different bodies: {', '.join(bodies)}.",
                    "affectedEntityType": "company",
                    "affectedEntityId": cin,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "isActive": True,
                },
                source="anomaly_detector:regulatory_recidivism",
                actor="system",
            )
            if result.success:
                alert_count += 1

        logger.info("Regulatory recidivism: %d alerts", alert_count)
        return alert_count


regulatory_recidivism_detector = RegulatoryRecidivismDetector()
