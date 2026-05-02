from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from api.middleware.auth import verify_api_key
from temporal.snapshot_engine import TemporalSnapshotEngine
from temporal.change_detector import ChangeDetector
from temporal.velocity_analyzer import VelocityAnalyzer
from temporal.rotation_tracker import RotationTracker
from temporal.precursor_model import PrecursorModel
from temporal.event_correlator import EventCorrelator

router = APIRouter(prefix="/temporal", tags=["temporal"])
_snap = TemporalSnapshotEngine()
_change = ChangeDetector()
_velocity = VelocityAnalyzer()
_rotation = RotationTracker()
_precursor = PrecursorModel()
_correlator = EventCorrelator()


@router.get("/entity/{entity_id}")
async def entity_at(
    entity_id: str,
    as_of: Optional[str] = Query(None, description="ISO datetime, e.g. 2024-01-01T00:00:00"),
    _key: str = Depends(verify_api_key),
):
    """Entity properties, optionally at a point in time."""
    ts = datetime.fromisoformat(as_of) if as_of else datetime.utcnow()
    return await _snap.get_entity_at(entity_id, ts)


@router.get("/director-history/{entity_id}")
async def director_history(entity_id: str, _key: str = Depends(verify_api_key)):
    """Full director appointment/resignation history for a company."""
    return {"entity_id": entity_id, "history": await _snap.get_director_history(entity_id)}


@router.get("/changes/{entity_id}")
async def recent_changes(
    entity_id: str,
    since_days: int = Query(90, ge=1, le=730),
    _key: str = Depends(verify_api_key),
):
    """Director and ownership changes in the last N days."""
    directors = await _change.detect_director_changes(entity_id, since_days)
    ownership = await _change.detect_ownership_changes(entity_id, since_days)
    return {"entity_id": entity_id, "director_changes": directors, "ownership_changes": ownership}


@router.get("/velocity/{entity_id}")
async def velocity(entity_id: str, _key: str = Depends(verify_api_key)):
    """Anomalous rate-of-change signals for an entity."""
    return await _velocity.analyze(entity_id)


@router.get("/rotating-directors")
async def rotating_directors(
    limit: int = Query(50, ge=1, le=200),
    _key: str = Depends(verify_api_key),
):
    """Directors who cycle rapidly between companies."""
    return {"rotating_directors": await _rotation.find_rotating_directors(limit)}


@router.get("/director-timeline/{director_id}")
async def director_timeline(director_id: str, _key: str = Depends(verify_api_key)):
    """Full chronological directorship history for a person."""
    return {"director_id": director_id, "timeline": await _rotation.get_director_timeline(director_id)}


@router.get("/precursor/{entity_id}")
async def precursor_risk(entity_id: str, _key: str = Depends(verify_api_key)):
    """CIRP precursor risk assessment for a company."""
    assessment = await _precursor.assess(entity_id)
    return assessment.to_dict()


@router.get("/timeline/{entity_id}")
async def entity_timeline(
    entity_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    _key: str = Depends(verify_api_key),
):
    """Chronological event timeline for an entity."""
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    events = await _correlator.get_entity_timeline(entity_id, start=start_dt, end=end_dt)
    return {"entity_id": entity_id, "events": events}
