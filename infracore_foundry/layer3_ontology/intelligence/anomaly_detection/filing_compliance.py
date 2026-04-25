import logging
from datetime import datetime, timezone
from storage.object_data_funnel import object_data_funnel
from core.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)


class FilingComplianceDetector:
    async def detect(self) -> int:
        """Flag active companies not updated in 2+ years."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT primary_key, properties->>'name' AS name
                        FROM ontology_objects
                        WHERE object_type = 'company'
                          AND is_deleted = FALSE
                          AND properties->>'status' = 'Active'
                          AND updated_at < NOW() - INTERVAL '2 years'
                    """)
                )
                rows = result.fetchall()
        except Exception as e:
            logger.error("Filing compliance query failed: %s", e)
            return 0

        alert_count = 0
        for row in rows:
            cin, name = row[0], row[1] or "Unknown"
            alert_id = f"FILING-{cin}"
            result = await object_data_funnel.write_object(
                object_type="alert",
                data={
                    "alertId": alert_id,
                    "severity": "MEDIUM",
                    "alertType": "FILING_COMPLIANCE",
                    "title": f"Non-Filer Alert: {name}",
                    "message": f"Active company {name} (CIN: {cin}) has not filed in over 2 years.",
                    "affectedEntityType": "company",
                    "affectedEntityId": cin,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "isActive": True,
                },
                source="anomaly_detector:filing_compliance",
                actor="system",
            )
            if result.success:
                alert_count += 1

        logger.info("Filing compliance: %d alerts", alert_count)
        return alert_count


filing_compliance_detector = FilingComplianceDetector()
