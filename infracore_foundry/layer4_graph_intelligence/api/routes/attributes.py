from fastapi import APIRouter, Depends, Query

from api.middleware.auth import verify_api_key
from shared_attributes.address_detector import SharedAddressDetector
from shared_attributes.director_detector import SharedDirectorDetector
from shared_attributes.owner_detector import SharedOwnerDetector

router = APIRouter(prefix="/attributes", tags=["shared-attributes"])
_addr = SharedAddressDetector()
_dir = SharedDirectorDetector()
_owner = SharedOwnerDetector()


@router.get("/shared-address/{entity_id}")
async def shared_address(entity_id: str, _key: str = Depends(verify_api_key)):
    """Entities sharing a registered address with entity_id."""
    return {"entity_id": entity_id, "shared_address_entities": await _addr.detect(entity_id)}


@router.get("/shared-directors/{entity_id}")
async def shared_directors(entity_id: str, _key: str = Depends(verify_api_key)):
    """Companies sharing directors with entity_id."""
    return {"entity_id": entity_id, "shared_director_companies": await _dir.detect(entity_id)}


@router.get("/shared-owners/{entity_id}")
async def shared_owners(entity_id: str, _key: str = Depends(verify_api_key)):
    """Entities sharing a beneficial owner with entity_id."""
    return {"entity_id": entity_id, "shared_owner_entities": await _owner.detect(entity_id)}


@router.get("/circular-ownership")
async def circular_ownership(
    limit: int = Query(50, ge=1, le=200),
    _key: str = Depends(verify_api_key),
):
    """Circular ownership cycles in the graph."""
    cycles = await _owner.detect_circular_ownership(limit=limit)
    return {"cycles": cycles, "count": len(cycles)}
