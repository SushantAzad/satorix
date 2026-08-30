"""Explicit Layer 2 processing route for the sealed local fixture."""
from fastapi import APIRouter, Depends, HTTPException

from layer1_ingestion.api.auth import require_api_key

router = APIRouter(prefix="/fixtures", tags=["Local synthetic fixtures"])


@router.post("/company-investigation/process", dependencies=[Depends(require_api_key)])
def process_company_investigation(body: dict) -> dict:
    if body != {"fixture_id": "company_investigation_v1"}:
        raise HTTPException(status_code=422, detail="Only company_investigation_v1 is supported")
    try:
        from layer2_pipeline.fixtures.company_investigation import process_fixture
        return process_fixture()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Fixture processing failed: {exc}") from exc
