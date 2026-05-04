"""Scenario simulation endpoints."""
import json
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Any, Optional

from analytics.scenario import scenario_simulator
from core.database import get_pool

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class ScenarioRequest(BaseModel):
    base_entity_type: str
    base_entity_id: str
    modifications: dict[str, Any]
    scenario_name: Optional[str] = None


@router.post("/simulate")
async def simulate_scenario(
    request: ScenarioRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
):
    result = await scenario_simulator.simulate(
        base_entity_type=request.base_entity_type,
        base_entity_id=request.base_entity_id,
        modifications=request.modifications,
        scenario_name=request.scenario_name or "",
        created_by=x_actor_id or "api_user",
    )
    return result


@router.get("/{scenario_id}")
async def get_scenario(scenario_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM l5_scenarios WHERE scenario_id=$1::uuid",
            scenario_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = dict(row)
    for field in ("modifications", "projected_outcomes"):
        if isinstance(result.get(field), str):
            result[field] = json.loads(result[field] or "{}")
    return result
