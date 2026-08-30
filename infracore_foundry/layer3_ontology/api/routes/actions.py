from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import Depends
from typing import Any
from core.database import get_db
from kinetic.workflow_engine import workflow_engine
from api.auth import require_platform_api_key
import json

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/{action_type_name}", dependencies=[Depends(require_platform_api_key)])
async def execute_action(
    action_type_name: str,
    parameters: dict[str, Any],
    request: Request,
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_role: str | None = Header(default=None, alias="X-Actor-Role"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, Any]:
    """Execute a governed Ontology Action on behalf of an authenticated actor.

    Actor identity is deliberately accepted only from trusted BFF headers,
    never query parameters supplied by an untrusted browser client.
    """
    if not x_actor_id or not x_actor_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Actor-Id and X-Actor-Role headers are required for Actions.",
        )
    result = await workflow_engine.execute_action(
        action_type_name=action_type_name,
        parameters=parameters,
        actor_id=x_actor_id,
        actor_role=x_actor_role,
        session_id=x_session_id,
        ip_address=request.client.host if request.client else None,
    )
    return {
        "success": result.success,
        "action_type": result.action_type,
        "action_id": result.action_id,
        "changes": result.changes,
        "side_effects": result.side_effects,
        "errors": result.errors,
        "executed_at": result.executed_at,
    }


@router.get("/history", dependencies=[Depends(require_platform_api_key)])
async def get_action_history(
    object_type: str | None = None,
    object_id: str | None = None,
    actor_id: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conditions = ["1=1"]
    params: dict[str, Any] = {"limit": limit}

    result = await db.execute(
        text("SELECT id, action_type, actor_id, actor_role, parameters, result, status, started_at FROM ontology_action_history ORDER BY started_at DESC LIMIT :limit"),
        params,
    )
    rows = result.fetchall()
    return {
        "total": len(rows),
        "history": [
            {
                "id": str(row[0]),
                "action_type": row[1],
                "actor_id": row[2],
                "actor_role": row[3],
                "parameters": row[4],
                "result": row[5],
                "status": row[6],
                "started_at": str(row[7]),
            }
            for row in rows
        ],
    }


@router.get("/types", dependencies=[Depends(require_platform_api_key)])
async def list_action_types() -> dict[str, Any]:
    return {"action_types": workflow_engine.list_action_types()}
