import logging
from datetime import datetime, timezone
from storage.object_data_funnel import object_data_funnel
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class CIRPContagionDetector:
    async def detect(self) -> int:
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (c1:Company {status: 'UnderCIRP'})-[:SHARES_DIRECTOR_WITH]-(c2:Company)
                WHERE c2.status <> 'UnderCIRP'
                RETURN c1.cin AS cirp_cin, c1.name AS cirp_name,
                       c2.cin AS affected_cin, c2.name AS affected_name
                """
            )
        except Exception as e:
            logger.error("CIRP contagion query failed: %s", e)
            return 0

        alert_count = 0
        for row in results:
            cirp_cin = row.get("cirp_cin", "")
            cirp_name = row.get("cirp_name", "")
            affected_cin = row.get("affected_cin", "")
            affected_name = row.get("affected_name", "")

            alert_id = f"CIRP-{cirp_cin}-{affected_cin}"
            result = await object_data_funnel.write_object(
                object_type="alert",
                data={
                    "alertId": alert_id,
                    "severity": "HIGH",
                    "alertType": "CIRP_CONTAGION",
                    "title": f"CIRP Contagion Risk: {affected_name}",
                    "message": f"Company {affected_name} (CIN: {affected_cin}) shares directors with {cirp_name} (CIN: {cirp_cin}), which is under CIRP. Contagion risk identified.",
                    "affectedEntityType": "company",
                    "affectedEntityId": affected_cin,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "isActive": True,
                },
                source="anomaly_detector:cirp_contagion",
                actor="system",
            )
            if result.success:
                alert_count += 1

        logger.info("CIRP contagion: %d alerts", alert_count)
        return alert_count


cirp_contagion_detector = CIRPContagionDetector()
