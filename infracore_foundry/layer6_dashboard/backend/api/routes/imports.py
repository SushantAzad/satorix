"""Authenticated CSV previews and explicit, replay-safe confirmation."""
import os
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from core.auth import RoleChecker
from core.database import get_db, L6ImportJob
from core.layer_clients import layer_clients
from shared.csv_import import parse_csv

router = APIRouter()
operator = RoleChecker(["platform_administrator", "data_steward"])


class Preview(BaseModel):
    kind: str
    csv_text: str = Field(max_length=256_000)
    mapping: dict[str, str] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=100)
    synthetic: bool = False


def tenant(user):
    cid = user.get("client_id")
    if not cid or cid == "PLATFORM_GLOBAL":
        raise HTTPException(403, "Imports require a private tenant")
    if os.getenv("LOCAL_SAFE_MODE", "true").lower() != "false" and os.getenv("DEVELOPMENT_MODE") != "true":
        raise HTTPException(403, "CSV imports are disabled in read-only Safe mode")
    return cid


async def upstream(payload, cid):
    try:
        response = await layer_clients.l3_client.post(
            "/ingest/csv", json=payload, headers={"X-Client-ID": cid}, timeout=120)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise HTTPException(502, "Ontology import service failed. Check saved import status before retrying.") from exc


@router.post("/preview")
async def preview(body: Preview, user=Depends(operator), db=Depends(get_db)):
    cid = tenant(user)
    try:
        parsed = parse_csv(body.kind, body.csv_text, body.mapping)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not body.mapping or parsed["errors"]:
        return {**parsed, "status": "mapping" if not body.mapping else "invalid"}
    payload = dict(kind=body.kind, rows=parsed["rows"], source=body.source.strip(),
                   sha256=parsed["sha256"], actor=user["sub"], synthetic=body.synthetic)
    validation = await upstream(payload, cid)
    if validation["errors"]:
        return {**parsed, **validation}
    job = L6ImportJob(user_id=UUID(user["sub"]), client_id=cid, payload=payload,
                      result=validation, status="ready")
    db.add(job)
    await db.commit()
    return {**parsed, **validation, "preview_rows": parsed["rows"], "import_id": str(job.id)}


@router.get("/")
async def history(user=Depends(operator), db=Depends(get_db)):
    cid = tenant(user)
    result = await db.execute(select(L6ImportJob).where(
        L6ImportJob.user_id == UUID(user["sub"]), L6ImportJob.client_id == cid
    ).order_by(L6ImportJob.created_at.desc()).limit(20))
    return [dict(import_id=str(j.id), status=j.status, source=j.payload["source"],
                 kind=j.payload["kind"], created_at=j.created_at.isoformat(), result=j.result)
            for j in result.scalars()]


@router.post("/{import_id}/commit")
async def commit(import_id: UUID, user=Depends(operator), db=Depends(get_db)):
    cid = tenant(user)
    result = await db.execute(select(L6ImportJob).where(
        L6ImportJob.id == import_id, L6ImportJob.user_id == UUID(user["sub"]),
        L6ImportJob.client_id == cid).with_for_update())
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Import not found")
    if job.status != "ready":
        return {"import_id": str(job.id), "status": job.status, **job.result}
    job.result = await upstream({**job.payload, "commit": True}, cid)
    job.status = job.result["status"]
    await db.commit()
    return {"import_id": str(job.id), **job.result}
