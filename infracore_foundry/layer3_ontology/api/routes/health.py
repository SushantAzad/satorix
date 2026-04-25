from fastapi import APIRouter
from typing import Any
from health.ontology_health import ontology_health_checker
from health.orphan_detector import orphan_detector
from health.impossible_state import impossible_state_detector
from health.duplicate_surface import duplicate_surface

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def service_health() -> dict[str, Any]:
    status: dict[str, Any] = {"status": "ok", "services": {}}

    # Check Neo4j
    try:
        from core.neo4j_client import neo4j_client
        await neo4j_client.run_query("RETURN 1 AS ping")
        status["services"]["neo4j"] = "ok"
    except Exception as e:
        status["services"]["neo4j"] = f"error: {e}"
        status["status"] = "degraded"

    # Check Elasticsearch
    try:
        from core.elasticsearch_client import es_client
        await es_client.client.ping()
        status["services"]["elasticsearch"] = "ok"
    except Exception as e:
        status["services"]["elasticsearch"] = f"error: {e}"
        status["status"] = "degraded"

    # Check Redis
    try:
        from core.redis_client import redis_client
        await redis_client.client.ping()
        status["services"]["redis"] = "ok"
    except Exception as e:
        status["services"]["redis"] = f"error: {e}"
        status["status"] = "degraded"

    # Check PostgreSQL
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        status["services"]["postgresql"] = "ok"
    except Exception as e:
        status["services"]["postgresql"] = f"error: {e}"
        status["status"] = "degraded"

    return status


@router.get("/ontology")
async def ontology_health() -> dict[str, Any]:
    report = await ontology_health_checker.generate_report()
    return {
        "total_objects": report.total_objects,
        "total_links": report.total_links,
        "property_coverage": report.property_coverage,
        "freshness_score": report.freshness_score,
        "stale_objects": report.stale_objects,
        "address_clusters": report.address_clusters,
        "address_cluster_count": len(report.address_clusters),
        "generated_at": report.generated_at,
    }


@router.get("/orphans")
async def get_orphans() -> dict[str, Any]:
    orphans = await orphan_detector.find_orphans()
    return {"orphan_count": len(orphans), "orphans": orphans}


@router.get("/impossible-states")
async def get_impossible_states() -> dict[str, Any]:
    violations = await impossible_state_detector.find_violations()
    return {"violation_count": len(violations), "violations": violations}


@router.get("/duplicates")
async def get_duplicates() -> dict[str, Any]:
    candidates = await duplicate_surface.find_candidates()
    return {"candidate_count": len(candidates), "candidates": candidates}
