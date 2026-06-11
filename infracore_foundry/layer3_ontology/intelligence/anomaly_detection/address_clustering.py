import logging
from datetime import datetime, timezone
from storage.object_data_funnel import object_data_funnel
from core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class AddressClusteringDetector:
    async def detect(self) -> int:
        try:
            results = await neo4j_client.run_query(
                """
                MATCH (a:Address)<-[:REGISTERED_AT]-(c:Company)
                WITH a, collect(c) AS companies, count(c) AS company_count
                WHERE company_count > 10
                RETURN a.normalizedAddress AS address, company_count,
                       [co IN companies | co.status] AS statuses
                """
            )
        except Exception as e:
            logger.error("Address clustering query failed: %s", e)
            return 0

        alert_count = 0
        for row in results:
            address = row.get("address", "")
            count = row.get("company_count", 0)
            statuses = row.get("statuses", [])
            suspicious = sum(1 for s in statuses if s in ("StrikeOff", "Dormant"))

            if suspicious < (count // 2):
                continue

            alert_id = f"ADDR-{abs(hash(address)) % 100000:05d}"
            result = await object_data_funnel.write_object(
                object_type="alert",
                data={
                    "alertId": alert_id,
                    "severity": "HIGH",
                    "alertType": "ADDRESS_CLUSTERING",
                    "title": f"Address Clustering: {count} companies at same address",
                    "message": f"Address '{address}' has {count} registered companies, majority ({suspicious}) are StrikeOff or Dormant — potential shell company cluster.",
                    "affectedEntityType": "address",
                    "affectedEntityId": address,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "isActive": True,
                },
                source="anomaly_detector:address_clustering",
                actor="system",
            )
            if result.success:
                alert_count += 1

        logger.info("Address clustering: %d alerts", alert_count)
        return alert_count


address_clustering_detector = AddressClusteringDetector()
