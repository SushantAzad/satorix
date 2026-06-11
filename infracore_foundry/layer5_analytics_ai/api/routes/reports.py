"""Report generation endpoints."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from analytics.report_generator import generate_due_diligence_report
from core.database import get_pool

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    entity_type: str
    entity_id: str
    report_type: str = "corporate_due_diligence"


@router.post("/generate")
async def generate_report_generic(
    request: GenerateReportRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    """
    Generic report generation endpoint called by Layer 6.
    Routes to the appropriate generator based on entity_type and report_type.
    Returns {report_id, status: "completed", report: {...}} synchronously.
    """
    actor_id = x_actor_id or "api_user"
    actor_role = x_actor_role or "Analyst"

    # For company due diligence: use full generator
    if request.entity_type.lower() == "company" and request.report_type in (
        "corporate_due_diligence", "regulatory_exposure"
    ):
        try:
            report = await generate_due_diligence_report(
                cin=request.entity_id,
                actor_id=actor_id,
                actor_role=actor_role,
            )
            return {"report_id": report["report_id"], "status": "completed", "report": report}
        except Exception as exc:
            # Return a structured fallback rather than crashing
            report_id = str(uuid.uuid4())
            return {
                "report_id": report_id,
                "status": "completed",
                "report": {
                    "report_id": report_id,
                    "report_type": request.report_type,
                    "entity_type": request.entity_type,
                    "entity_id": request.entity_id,
                    "title": f"Intelligence Report — {request.entity_id}",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "generated_by": actor_id,
                    "sections": {
                        "executive_summary": f"Report generation encountered an error: {exc}. Please retry or check Layer 3/4 connectivity.",
                        "entity_profile": {"entity_id": request.entity_id, "entity_type": request.entity_type},
                    },
                },
            }

    # For other types (director, project, portfolio_health, peer_comparison): generate intelligence report
    from llm.workflows.summarization import generate_entity_intelligence
    report_id = str(uuid.uuid4())
    try:
        summary = await generate_entity_intelligence(
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            context={},
            actor_id=actor_id,
            actor_role=actor_role,
        )
    except Exception as exc:
        summary = f"Intelligence summary unavailable: {exc}"

    report = {
        "report_id": report_id,
        "report_type": request.report_type,
        "entity_type": request.entity_type,
        "entity_id": request.entity_id,
        "title": f"{request.report_type.replace('_', ' ').title()} — {request.entity_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": actor_id,
        "sections": {"executive_summary": summary},
    }

    # Persist
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO l5_reports
                    (report_id, report_type, entity_type, entity_id, title, content_json, generated_by)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                report_id, request.report_type, request.entity_type, request.entity_id,
                report["title"], json.dumps(report, default=str), actor_id,
            )
    except Exception as exc:
        pass  # Non-fatal — return report even if persistence fails

    return {"report_id": report_id, "status": "completed", "report": report}


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
