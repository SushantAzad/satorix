"""
Reports routes — trigger, poll, list, and delete generated reports.
"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aggregators.report import (
    REPORT_TYPES,
    _delete_report,
    _list_user_reports,
    generate_report,
    poll_report,
)
from core.auth import get_current_user
from core.database import get_db
from core.layer_clients import layer_clients

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class GenerateReportRequest(BaseModel):
    entity_type: str
    entity_id: str
    report_type: str
    depth: int = 2


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/generate")
async def trigger_report(
    body: GenerateReportRequest,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Trigger report generation via Layer 5.
    Returns immediately with {report_id, status: "pending"} or cached result.
    """
    if body.report_type not in REPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"report_type must be one of: {sorted(REPORT_TYPES)}",
        )

    result = await generate_report(
        layer_clients,
        db,
        user_id=current_user["sub"],
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        report_type=body.report_type,
        depth=body.depth,
    )
    return result


@router.get("/")
async def list_reports(
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict]:
    """List the current user's recent reports from l6_report_cache."""
    return await _list_user_reports(db, current_user["sub"])


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    report_type: Optional[str] = None,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Check the status of a report and return its content when ready."""
    result = await poll_report(
        layer_clients,
        db,
        user_id=current_user["sub"],
        report_id=report_id,
        entity_type=entity_type,
        entity_id=entity_id,
        report_type=report_type,
    )
    if result.get("status") == "unknown":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    return result


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Remove a report from the cache."""
    deleted = await _delete_report(db, report_id, current_user["sub"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found or not owned by current user.",
        )
    return {"message": "Report deleted.", "report_id": report_id}
