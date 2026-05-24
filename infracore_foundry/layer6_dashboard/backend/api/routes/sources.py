"""
Sources routes — proxy to Layer 1 API for connector management.
"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.auth import RoleChecker, get_current_user
from core.layer_clients import layer_clients

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateSourceRequest(BaseModel):
    source_name: str
    source_type: str
    config: Dict
    client_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/")
async def list_sources(
    current_user: Dict = Depends(get_current_user),
) -> List[Dict]:
    """List all configured data sources from Layer 1."""
    client_id = current_user.get("client_id")
    sources = await layer_clients.get_sources(client_id=client_id)
    return sources or []


@router.post("/")
async def create_source(
    body: CreateSourceRequest,
    current_user: Dict = Depends(
        RoleChecker(["platform_administrator", "data_steward"])
    ),
) -> Dict:
    """Create a new data source connector via Layer 1."""
    payload = {
        "source_name": body.source_name,
        "source_type": body.source_type,
        "config": body.config,
        "client_id": body.client_id or current_user.get("client_id", "default"),
    }
    result = await layer_clients.create_source(payload)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Layer 1 API unavailable. Could not create source.",
        )
    return result


@router.post("/{source_id}/test")
async def test_source(
    source_id: str,
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Test a data source connection via Layer 1."""
    result = await layer_clients.test_source(source_id)
    if result is None:
        return {
            "source_id": source_id,
            "status": "unknown",
            "message": "Layer 1 API unavailable.",
        }
    return result


@router.get("/{source_id}/health")
async def get_source_health(
    source_id: str,
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Return health status for a specific data source."""
    source = await layer_clients.get_source_by_id(source_id)
    if source is None:
        return {
            "source_id": source_id,
            "status": "unknown",
            "message": "Layer 1 API unavailable or source not found.",
        }
    return source


@router.post("/{source_id}/sync")
async def trigger_sync(
    source_id: str,
    current_user: Dict = Depends(
        RoleChecker(["platform_administrator", "data_steward", "analyst"])
    ),
) -> Dict:
    """Trigger an immediate sync for the given data source."""
    result = await layer_clients.trigger_ingest(source_id)
    if result is None:
        return {"triggered": False, "message": "Layer 1 API unavailable. Sync could not be triggered."}
    return {"triggered": True, **result}


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    current_user: Dict = Depends(
        RoleChecker(["platform_administrator", "data_steward"])
    ),
) -> Dict:
    """Remove a data source connector."""
    try:
        resp = await layer_clients.l1_client.delete(f"/api/v1/sources/{source_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
        if resp.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Layer 1 API error.")
        return {"deleted": True, "source_id": source_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("delete_source(%s) failed: %s", source_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Layer 1 API unavailable.")
