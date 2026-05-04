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
    result = await layer_clients.create_source(body.model_dump())
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
