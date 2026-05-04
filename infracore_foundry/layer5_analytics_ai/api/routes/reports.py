"""Report generation endpoints."""
import json
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from analytics.report_generator import generate_due_diligence_report
from core.database import get_pool

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/due-diligence/{cin}")
async def generate_due_diligence(
    cin: str,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    report = await generate_due_diligence_report(
        cin=cin,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
    )
    return {"report_id": report["report_id"], "title": report["title"], "report": report}


@router.get("/{report_id}")
async def get_report(report_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT content_json, title, created_at FROM l5_reports WHERE report_id=$1::uuid",
            report_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    content = row["content_json"] if isinstance(row["content_json"], dict) else json.loads(row["content_json"] or "{}")
    return {"report_id": report_id, "title": row["title"], "created_at": row["created_at"].isoformat(), "report": content}


@router.get("/entity/{entity_type}/{entity_id}")
async def list_entity_reports(entity_type: str, entity_id: str, limit: int = 10):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT report_id, report_type, title, created_at FROM l5_reports WHERE entity_type=$1 AND entity_id=$2 ORDER BY created_at DESC LIMIT $3",
            entity_type, entity_id, limit,
        )
    return {"reports": [dict(r) for r in rows]}
