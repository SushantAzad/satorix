"""Error record (dead letter queue) management routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer2_pipeline.errors.quarantine import QuarantineManager

router = APIRouter(prefix="/errors", tags=["Error Management"])


@router.get("/", dependencies=[Depends(require_api_key)])
def list_errors(
    run_id: UUID = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    mgr = QuarantineManager(db)
    records = mgr.get_quarantined(run_id=run_id, limit=limit)
    return [_to_dict(r) for r in records]


@router.post("/{error_id}/reprocess", dependencies=[Depends(require_api_key)])
def mark_reprocessed(error_id: UUID, note: str = "", db: Session = Depends(get_db)):
    mgr = QuarantineManager(db)
    record = mgr.mark_reprocessed(error_id, note)
    if record is None:
        raise HTTPException(status_code=404, detail="Error record not found")
    return _to_dict(record)


@router.post("/{error_id}/discard", dependencies=[Depends(require_api_key)])
def mark_discarded(error_id: UUID, note: str = "", db: Session = Depends(get_db)):
    mgr = QuarantineManager(db)
    record = mgr.mark_discarded(error_id, note)
    if record is None:
        raise HTTPException(status_code=404, detail="Error record not found")
    return _to_dict(record)


def _to_dict(r) -> dict:
    return {
        "id": str(r.id),
        "run_id": str(r.run_id),
        "step_id": r.step_id,
        "error_type": r.error_type,
        "error_subtype": r.error_subtype,
        "severity": r.severity,
        "error_message": r.error_message,
        "retry_count": r.retry_count,
        "status": r.status,
        "created_at": r.created_at,
        "resolved_at": r.resolved_at,
        "resolution_note": r.resolution_note,
    }
