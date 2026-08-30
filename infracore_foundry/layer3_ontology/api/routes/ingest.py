import uuid
from fastapi import APIRouter, Query
from typing import Any
from ingestion.batch_ingestor import batch_ingestor

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_running_ingest_jobs: dict[str, Any] = {}


@router.post("/fixture")
async def ingest_fixture_manifest(body: dict[str, Any]) -> dict[str, Any]:
    if set(body) != {"fixture_id", "manifest_bucket", "manifest_key"} or body.get("fixture_id") != "company_investigation_v1":
        return {"status": "rejected", "error": "Only the sealed company fixture manifest is accepted"}
    from ingestion.fixture_ingestor import ingest_company_fixture
    return await ingest_company_fixture(body["manifest_bucket"], body["manifest_key"])


@router.post("/trigger")
async def trigger_ingestion(
    body: dict[str, Any],
    actor_role: str = Query(default="system_pipeline"),
) -> dict[str, Any]:
    client_id = body.get("client_id", "infracore")
    source_ids = body.get("source_ids")
    ingest_id = str(uuid.uuid4())

    summary = await batch_ingestor.ingest_from_layer2(
        client_id=client_id,
        source_ids=source_ids,
    )
    _running_ingest_jobs[ingest_id] = {"status": "completed", "summary": summary}

    return {
        "ingest_id": ingest_id,
        "status": "completed",
        "summary": {
            "objects_processed": summary.objects_processed,
            "objects_created": summary.objects_created,
            "objects_updated": summary.objects_updated,
            "objects_unchanged": summary.objects_unchanged,
            "links_created": summary.links_created,
            "inferred_links_created": summary.inferred_links_created,
            "alerts_created": summary.alerts_created,
            "risk_scores_updated": summary.risk_scores_updated,
            "errors": summary.errors[:10],
            "duration_seconds": summary.duration_seconds,
        },
    }


@router.get("/status/{ingest_id}")
async def get_ingest_status(ingest_id: str) -> dict[str, Any]:
    job = _running_ingest_jobs.get(ingest_id)
    if not job:
        return {"ingest_id": ingest_id, "status": "not_found"}
    return {"ingest_id": ingest_id, **job}


@router.post("/full-refresh")
async def full_refresh(
    confirmed: bool = Query(default=False),
    actor_role: str = Query(default="platform_administrator"),
) -> dict[str, Any]:
    if actor_role != "platform_administrator":
        return {"error": "Only PLATFORM_ADMINISTRATOR can run full refresh"}
    if not confirmed:
        return {"warning": "Set confirmed=true to proceed with destructive full refresh"}

    # Run full ingestion
    summary = await batch_ingestor.ingest_from_layer2()
    return {"status": "completed", "objects_created": summary.objects_created}
