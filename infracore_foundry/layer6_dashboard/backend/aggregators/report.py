"""Persisted, owner- and tenant-scoped available-data due diligence."""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.sql import text
from shared.relationship_exposure import relationship_exposure

REPORT_TYPES = {"corporate_due_diligence"}


async def _save_report_cache(db, user_id, entity_type, entity_id, report_type, content):
    report_id = str(uuid.uuid4())
    try:
        await db.execute(text("""
            INSERT INTO l6_report_cache
                (id, user_id, entity_type, entity_id, report_type,
                 report_content, generated_at, expires_at)
            VALUES (:id, :user_id, :entity_type, :entity_id, :report_type,
                    CAST(:content AS jsonb), NOW(), :expires_at)
        """), dict(id=report_id, user_id=user_id, entity_type=entity_type,
                   entity_id=entity_id, report_type=report_type, content=json.dumps(content),
                   expires_at=datetime.now(timezone.utc) + timedelta(hours=24)))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report_id


async def _list_user_reports(db, user_id, client_id):
    result = await db.execute(text("""
        SELECT id, entity_type, entity_id, report_type, generated_at, expires_at
        FROM l6_report_cache WHERE user_id = :user_id
          AND report_content->>'client_id' = :client_id AND expires_at > NOW()
        ORDER BY generated_at DESC LIMIT 50
    """), dict(user_id=user_id, client_id=client_id))
    return [dict(report_id=str(r.id), entity_type=r.entity_type, entity_id=r.entity_id,
                 report_type=r.report_type, generated_at=r.generated_at.isoformat(),
                 expires_at=r.expires_at.isoformat(), status="completed")
            for r in result.fetchall()]


async def poll_report(clients, db, user_id, report_id, client_id, **_):
    result = await db.execute(text("""
        SELECT * FROM l6_report_cache WHERE id = :id AND user_id = :user_id
          AND report_content->>'client_id' = :client_id AND expires_at > NOW()
    """), dict(id=report_id, user_id=user_id, client_id=client_id))
    r = result.fetchone()
    if not r:
        return dict(report_id=report_id, status="unknown")
    return dict(report_id=str(r.id), status="completed", report_content=r.report_content,
                entity_type=r.entity_type, entity_id=r.entity_id, report_type=r.report_type,
                generated_at=r.generated_at.isoformat(), expires_at=r.expires_at.isoformat())


async def _delete_report(db, report_id, user_id, client_id):
    result = await db.execute(text("""
        DELETE FROM l6_report_cache WHERE id = :id AND user_id = :user_id
          AND report_content->>'client_id' = :client_id
    """), dict(id=report_id, user_id=user_id, client_id=client_id))
    await db.commit()
    return result.rowcount > 0


async def generate_report(clients, db, user_id, entity_type, entity_id,
                          report_type, depth=2, client_id=None):
    if report_type not in REPORT_TYPES or not client_id:
        raise ValueError("Supported report type and tenant context are required.")
    # Fresh snapshots avoid hiding changed risk behind yesterday's cached report.
    entity = await clients.get_entity(entity_type, entity_id, client_id=client_id)
    if not entity:
        raise LookupError("Entity not found or ontology unavailable; no report was created.")
    network, risk = await asyncio.gather(
        clients.get_network(entity_type, entity_id, depth=depth, client_id=client_id),
        clients.get_risk_score(entity_type, entity_id, client_id=client_id))
    props = entity.get("properties", entity)
    synthetic = bool(props.get("synthetic"))
    score = risk.get("risk_score") if risk else None
    limitations = [
        "Available-data snapshot only, not a completed independent due-diligence investigation.",
        "No external filings, sanctions searches, financial verification or LLM analysis were performed.",
        "Missing data and absent relationships do not establish low risk or regulatory clearance.",
        f"Graph coverage is limited to loaded relationships within depth {depth}.",
    ]
    if synthetic:
        limitations.insert(0, "SYNTHETIC TEST DATA — not real company findings or a production risk assessment.")
    if network is None:
        limitations.append("Network service unavailable; relationship coverage is unknown.")
    if score is None:
        limitations.append("Risk assessment unavailable; unknown is not zero.")
    content = dict(
        schema_version="due-diligence/v1", client_id=client_id,
        title=f"Due Diligence — {props.get('name') or props.get('companyName') or entity_id}",
        entity_type=entity_type, entity_id=entity_id, report_type=report_type,
        generated_at=datetime.now(timezone.utc).isoformat(),
        synthetic=synthetic, coverage="partial", depth=depth,
        sections={
            "executive_summary": {
                "assessment": "Available-data review only", "risk_score": score,
                "risk_band": risk.get("risk_band", "NONE") if risk and score is not None else "NONE",
                "explanation": props.get("riskExplanation") or "Recorded risk reproduced without independent validation.",
            },
            "entity_record": entity,
            "relationship_exposure": relationship_exposure(entity_type, entity_id, network),
            "risk_assessment": risk or {"status": "unavailable", "score": None},
            "relationship_snapshot": network if network is not None else {"status": "unavailable"},
            "provenance": {
                "source": "Layer 3 ontology record and graph",
                "record_version": props.get("_version"),
                "record_updated_at": props.get("_updated_at"),
                "note": "Source IDs and relationship evidence are retained above; original sources are not independently verified.",
            },
            "limitations": limitations,
            "review_checklist": [
                "Verify identity and source filings.",
                "Confirm directors, ownership and beneficial owners.",
                "Obtain current financial statements and validate risk inputs.",
                "Perform authorized regulatory, litigation and sanctions checks.",
            ],
        })
    report_id = await _save_report_cache(db, user_id, entity_type, entity_id, report_type, content)
    return await poll_report(clients, db, user_id, report_id, client_id)
