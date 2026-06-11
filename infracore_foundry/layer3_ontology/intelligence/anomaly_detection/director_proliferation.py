import uuid
import logging
from datetime import datetime, timezone
from storage.object_data_funnel import object_data_funnel
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class DirectorProliferationDetector:
    async def detect(self) -> int:
        """Flag directors with >15 current directorships."""
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (d:Director)
                WHERE d.currentDirectorships > 15
                RETURN d.din AS din, d.name AS name, d.currentDirectorships AS count
                """
            )
        except Exception as e:
            logger.error("Director proliferation query failed: %s", e)
            return 0

        alert_count = 0
        for row in results:
            din = row.get("din", "")
            name = row.get("name", "")
            count = row.get("count", 0)
            alert_id = f"DPRO-{din}"
            result = await object_data_funnel.write_object(
                object_type="alert",
                data={
                    "alertId": alert_id,
                    "severity": "HIGH",
                    "alertType": "DIRECTOR_PROLIFERATION",
                    "title": f"Director Proliferation: {name}",
                    "message": f"Director {name} (DIN: {din}) holds {count} current directorships, exceeding the suspicious threshold of 15.",
                    "affectedEntityType": "director",
                    "affectedEntityId": din,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "isActive": True,
                },
                source="anomaly_detector:director_proliferation",
                actor="system",
            )
            if result.success:
                alert_count += 1

        logger.info("Director proliferation: %d alerts", alert_count)
        return alert_count


director_proliferation_detector = DirectorProliferationDetector()
