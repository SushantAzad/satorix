from fastapi import APIRouter, Query, HTTPException
from typing import Any, Optional
from datetime import datetime
from timeline.timeline_service import timeline_service

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("/{object_type}/{primary_key}")
async def get_timeline(
    object_type: str,
    primary_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    events = await timeline_service.get_object_timeline(object_type, primary_key, start, end)
    return {
        "object_type": object_type,
        "primary_key": primary_key,
        "event_count": len(events),
        "events": [
            {**e, "occurred_at": str(e.get("occurred_at", "")),
             "old_value": e.get("old_value"),
             "new_value": e.get("new_value")}
            for e in events
        ],
    }


@router.get("/{object_type}/{primary_key}/property/{property_name}")
async def get_property_history(
    object_type: str,
    primary_key: str,
    property_name: str,
) -> dict[str, Any]:
    history = await timeline_service.get_property_history(object_type, primary_key, property_name)
    return {
        "object_type": object_type,
        "primary_key": primary_key,
        "property_name": property_name,
        "history": history,
    }


@router.get("/{object_type}/{primary_key}/snapshot")
async def get_snapshot(
    object_type: str,
    primary_key: str,
    as_of: str = Query(..., description="ISO 8601 datetime"),
) -> dict[str, Any]:
    try:
        as_of_dt = datetime.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(status_code=400, detail="as_of must be ISO 8601 datetime")

    snapshot = await timeline_service.get_object_at_time(object_type, primary_key, as_of_dt)
    return {
        "object_type": object_type,
        "primary_key": primary_key,
        "as_of": as_of,
        "snapshot": snapshot,
    }
