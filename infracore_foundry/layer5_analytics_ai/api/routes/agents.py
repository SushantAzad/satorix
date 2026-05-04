"""Agent execution endpoints."""
import json
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from agents.agents.due_diligence import DueDiligenceAgent
from agents.agents.entity_resolution import EntityResolutionAgent
from core.database import get_pool

router = APIRouter(prefix="/agents", tags=["agents"])


class DueDiligenceRequest(BaseModel):
    cin: str
    depth: int = 2


class EntityResolutionRequest(BaseModel):
    cin: str


@router.post("/due-diligence")
async def run_due_diligence(
    request: DueDiligenceRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
):
    agent = DueDiligenceAgent()
    result = await agent.run(
        input_params={"cin": request.cin, "depth": request.depth},
        actor_id=x_actor_id or "api_user",
    )
    return result


@router.post("/entity-resolution")
async def run_entity_resolution(
    request: EntityResolutionRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
):
    agent = EntityResolutionAgent()
    result = await agent.run(
        input_params={"cin": request.cin},
        actor_id=x_actor_id or "api_user",
    )
    return result


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM l5_agent_runs WHERE run_id=$1::uuid",
            run_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Agent run not found")
    result = dict(row)
    for field in ("input_params", "execution_trace", "guardrail_triggers"):
        if isinstance(result.get(field), str):
            result[field] = json.loads(result[field] or "[]")
    return result


@router.get("/runs")
async def list_agent_runs(agent_type: Optional[str] = None, limit: int = 20):
    pool = get_pool()
    async with pool.acquire() as conn:
        if agent_type:
            rows = await conn.fetch(
                "SELECT run_id, agent_type, actor_id, status, output_summary, created_at FROM l5_agent_runs WHERE agent_type=$1 ORDER BY created_at DESC LIMIT $2",
                agent_type, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT run_id, agent_type, actor_id, status, output_summary, created_at FROM l5_agent_runs ORDER BY created_at DESC LIMIT $1",
                limit,
            )
    return {"runs": [dict(r) for r in rows]}
