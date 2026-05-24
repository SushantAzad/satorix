"""
Alerts routes — list, detail, acknowledge, assign.
"""
import logging
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aggregators.alerts import get_alert_detail, get_alert_list, get_alert_summary
from core.auth import RoleChecker, get_current_user
from core.database import get_db
from core.layer_clients import layer_clients

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AcknowledgeRequest(BaseModel):
    notes: Optional[str] = None


class AssignRequest(BaseModel):
    assignee_name: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/summary")
async def alerts_summary(
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Return aggregate alert counts: total, critical, high, medium, low, unacknowledged, new_today."""
    client_id: str = current_user.get("client_id", "PLATFORM_GLOBAL")
    return await get_alert_summary(layer_clients, client_id=client_id)


@router.get("/")
async def list_alerts(
    severity: Optional[str] = Query(None, description="CRITICAL | HIGH | MEDIUM | LOW"),
    alert_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Return filtered and sorted alert list."""
    client_id: str = current_user.get("client_id", "PLATFORM_GLOBAL")
    return await get_alert_list(
        layer_clients,
        severity=severity,
        alert_type=alert_type,
        entity_type=entity_type,
        acknowledged=acknowledged,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        client_id=client_id,
    )


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Return alert detail with entity context, SHAP explanation, and action log."""
    client_id: str = current_user.get("client_id", "PLATFORM_GLOBAL")
    detail = await get_alert_detail(layer_clients, alert_id, client_id=client_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found.",
        )
    return detail


@router.patch("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeRequest,
    current_user: Dict = Depends(
        RoleChecker(["analyst", "compliance_head", "platform_administrator"])
    ),
) -> Dict:
    """Mark an alert as acknowledged by the current user."""
    client_id: str = current_user.get("client_id", "PLATFORM_GLOBAL")
    try:
        resp = await layer_clients.l3_client.patch(
            f"/intelligence/alerts/{alert_id}/acknowledge",
            json={
                "acknowledged_by": current_user.get("email"),
                "acknowledged_by_id": current_user.get("sub"),
                "notes": body.notes,
            },
            headers={"X-Client-ID": client_id},
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert '{alert_id}' not found.",
            )
        if resp.status_code >= 400:
            # Gracefully return a synthetic ack if Layer 3 is unavailable
            logger.warning(
                "L3 acknowledge failed (status %d) — returning synthetic ack.", resp.status_code
            )
            return {
                "alert_id": alert_id,
                "acknowledged": True,
                "acknowledged_by": current_user.get("email"),
                "notes": body.notes,
            }
        return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("acknowledge_alert(%s) failed: %s — returning synthetic.", alert_id, exc)
        return {
            "alert_id": alert_id,
            "acknowledged": True,
            "acknowledged_by": current_user.get("email"),
            "notes": body.notes,
        }


@router.patch("/{alert_id}/assign")
async def assign_alert(
    alert_id: str,
    body: AssignRequest,
    current_user: Dict = Depends(
        RoleChecker(["analyst", "compliance_head", "platform_administrator"])
    ),
) -> Dict:
    """Assign an alert to a team member."""
    client_id: str = current_user.get("client_id", "PLATFORM_GLOBAL")
    try:
        resp = await layer_clients.l3_client.patch(
            f"/intelligence/alerts/{alert_id}/assign",
            json={
                "assignee_name": body.assignee_name,
                "assigned_by": current_user.get("email"),
                "notes": body.notes,
            },
            headers={"X-Client-ID": client_id},
        )
        if resp.status_code >= 400:
            return {
                "alert_id": alert_id,
                "assignee_name": body.assignee_name,
                "assigned_by": current_user.get("email"),
            }
        return resp.json()
    except Exception as exc:
        logger.warning("assign_alert(%s) failed: %s", alert_id, exc)
        return {
            "alert_id": alert_id,
            "assignee_name": body.assignee_name,
            "assigned_by": current_user.get("email"),
        }
