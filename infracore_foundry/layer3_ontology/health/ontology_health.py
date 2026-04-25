from dataclasses import dataclass, field
from typing import Any
import logging
from core.database import AsyncSessionLocal
from core.neo4j_client import neo4j_client
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

CRITICAL_PROPERTIES: dict[str, list[str]] = {
    "company": ["cin", "name", "status", "registeredState", "riskScore"],
    "director": ["din", "name", "nationality", "disqualificationStatus"],
    "project": ["projectId", "name", "status", "totalCost"],
}


@dataclass
class OntologyHealthReport:
    total_objects: int = 0
    total_links: int = 0
    property_coverage: dict[str, dict[str, float]] = field(default_factory=dict)
    relationship_coverage: list[dict] = field(default_factory=list)
    freshness_score: float = 0.0
    stale_objects: int = 0
    orphan_count: int = 0
    impossible_state_count: int = 0
    address_clusters: list[dict] = field(default_factory=list)
    generated_at: str = ""


class OntologyHealthChecker:
    async def generate_report(self) -> OntologyHealthReport:
        report = OntologyHealthReport()
        from datetime import datetime, timezone
        report.generated_at = datetime.now(timezone.utc).isoformat()

        async with AsyncSessionLocal() as db:
            # Total objects
            result = await db.execute(
                text("SELECT COUNT(*) FROM ontology_objects WHERE is_deleted = FALSE")
            )
            report.total_objects = result.scalar() or 0

            # Total links
            result = await db.execute(
                text("SELECT COUNT(*) FROM ontology_links WHERE is_deleted = FALSE")
            )
            report.total_links = result.scalar() or 0

            # Property coverage per type
            for obj_type, critical_props in CRITICAL_PROPERTIES.items():
                result = await db.execute(
                    text("SELECT properties FROM ontology_objects WHERE object_type = :ot AND is_deleted = FALSE"),
                    {"ot": obj_type},
                )
                rows = result.fetchall()
                if not rows:
                    continue

                coverage: dict[str, float] = {}
                for prop in critical_props:
                    count = sum(
                        1 for row in rows
                        if (row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")).get(prop) is not None
                    )
                    coverage[prop] = round((count / len(rows)) * 100, 2)
                report.property_coverage[obj_type] = coverage

            # Freshness
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM ontology_objects
                    WHERE is_deleted = FALSE AND updated_at >= NOW() - INTERVAL '30 days'
                """)
            )
            recent = result.scalar() or 0
            if report.total_objects > 0:
                report.freshness_score = round((recent / report.total_objects) * 100, 2)

            # Stale objects
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM ontology_objects
                    WHERE is_deleted = FALSE AND updated_at < NOW() - INTERVAL '60 days'
                """)
            )
            report.stale_objects = result.scalar() or 0

        # Address clusters from Neo4j
        try:
            cluster_results = await neo4j_client.run_query(
                """
                MATCH (a:Address)<-[:REGISTERED_AT]-(c:Company)
                WITH a, collect(c.cin) AS cins, count(c) AS company_count
                WHERE company_count > 5
                RETURN a.normalizedAddress AS address, company_count, cins
                ORDER BY company_count DESC
                LIMIT 10
                """
            )
            report.address_clusters = [
                {
                    "address": r.get("address"),
                    "company_count": r.get("company_count"),
                    "companies": r.get("cins", []),
                }
                for r in cluster_results
            ]
        except Exception as e:
            logger.warning("Address cluster query failed: %s", e)

        return report


ontology_health_checker = OntologyHealthChecker()
