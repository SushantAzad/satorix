from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Any, Optional
import json
from core.database import get_db
from core.client_context import get_client_id, PLATFORM_GLOBAL
from storage.object_data_funnel import object_data_funnel
from storage.cache_store import CacheStore
from dynamic.object_security import object_security_filter

router = APIRouter(prefix="/objects", tags=["objects"])
_cache = CacheStore()


@router.get("/{object_type}")
async def list_objects(
    object_type: str,
    status: Optional[str] = None,
    state: Optional[str] = None,
    riskScore_min: Optional[int] = None,
    riskScore_max: Optional[int] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    actor_role: str = Query(default="analyst"),
    db: AsyncSession = Depends(get_db),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    # Return objects owned by this client OR PLATFORM_GLOBAL public data.
    conditions = [
        "object_type = :ot",
        "is_deleted = FALSE",
        "(client_id = :cid OR client_id = :pg)",
    ]
    params: dict[str, Any] = {
        "ot": object_type.lower(),
        "cid": client_id,
        "pg": PLATFORM_GLOBAL,
        "limit": limit,
        "offset": offset,
    }

    if status:
        conditions.append("properties->>'status' = :status")
        params["status"] = status
    if state:
        conditions.append("(properties->>'registeredState' = :state OR properties->>'state' = :state)")
        params["state"] = state
    if riskScore_min is not None:
        conditions.append("(properties->>'riskScore')::int >= :rs_min")
        params["rs_min"] = riskScore_min
    if riskScore_max is not None:
        conditions.append("(properties->>'riskScore')::int <= :rs_max")
        params["rs_max"] = riskScore_max

    where_clause = " AND ".join(conditions)
    result = await db.execute(
        text(
            f"SELECT primary_key, properties, version, updated_at "
            f"FROM ontology_objects WHERE {where_clause} "
            f"ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = result.fetchall()

    objects = []
    for row in rows:
        props = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
        filtered = object_security_filter.filter_object(object_type, props, actor_role)
        objects.append({
            "primary_key": row[0],
            "version": row[2],
            "updated_at": str(row[3]),
            **filtered,
        })

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ontology_objects WHERE {where_clause}"),
        count_params,
    )
    total = count_result.scalar() or 0

    return {"total": total, "offset": offset, "limit": limit, "items": objects}


@router.get("/{object_type}/{primary_key}")
async def get_object(
    object_type: str,
    primary_key: str,
    actor_role: str = Query(default="analyst"),
    db: AsyncSession = Depends(get_db),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    # The legacy object cache is not tenant-keyed. Authorize every detail read
    # against the database rather than returning another tenant's cached object.

    result = await db.execute(
        text(
            "SELECT properties, version, updated_at FROM ontology_objects "
            "WHERE object_type = :ot AND primary_key = :pk "
            "AND (client_id = :cid OR client_id = :pg) "
            "AND is_deleted = FALSE"
        ),
        {"ot": object_type.lower(), "pk": primary_key, "cid": client_id, "pg": PLATFORM_GLOBAL},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{object_type}/{primary_key} not found")

    props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    props["_version"] = row[1]
    props["_updated_at"] = str(row[2])

    return object_security_filter.filter_object(object_type, props, actor_role)


@router.post("/{object_type}")
async def create_object(
    object_type: str,
    data: dict[str, Any],
    actor_id: str = Query(default="anonymous"),
    actor_role: str = Query(default="data_steward"),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    result = await object_data_funnel.write_object(
        object_type=object_type,
        data=data,
        source="user_api",
        actor=actor_id,
        client_id=client_id,
    )
    if not result.success:
        raise HTTPException(status_code=422, detail=result.errors)
    return {"success": True, "object_id": result.object_id, "version": result.version}


@router.put("/{object_type}/{primary_key}")
async def update_object(
    object_type: str,
    primary_key: str,
    updates: dict[str, Any],
    actor_id: str = Query(default="anonymous"),
    actor_role: str = Query(default="data_steward"),
    db: AsyncSession = Depends(get_db),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    result_row = await db.execute(
        text(
            "SELECT properties FROM ontology_objects "
            "WHERE object_type = :ot AND primary_key = :pk "
            "AND (client_id = :cid OR client_id = :pg) "
            "AND is_deleted = FALSE"
        ),
        {"ot": object_type.lower(), "pk": primary_key, "cid": client_id, "pg": PLATFORM_GLOBAL},
    )
    row = result_row.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{object_type}/{primary_key} not found")

    existing = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    merged = {**existing, **updates}

    result = await object_data_funnel.write_object(
        object_type=object_type,
        data=merged,
        source="user_api:update",
        actor=actor_id,
        client_id=client_id,
    )
    if not result.success:
        raise HTTPException(status_code=422, detail=result.errors)
    return {"success": True, "object_id": result.object_id, "version": result.version, "changes": len(result.changes)}


@router.delete("/{object_type}/{primary_key}")
async def delete_object(
    object_type: str,
    primary_key: str,
    reason: str = Query(default="Deleted by administrator"),
    actor_id: str = Query(default="anonymous"),
    actor_role: str = Query(default="platform_administrator"),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    if actor_role.lower() != "platform_administrator":
        raise HTTPException(status_code=403, detail="Only PLATFORM_ADMINISTRATOR can delete objects")
    result = await object_data_funnel.delete_object(
        object_type=object_type,
        primary_key=primary_key,
        actor=actor_id,
        reason=reason,
        client_id=client_id,
    )
    if not result.success:
        raise HTTPException(status_code=422, detail=result.errors)
    return {"success": True, "archived": primary_key}
