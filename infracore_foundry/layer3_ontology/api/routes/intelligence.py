from fastapi import APIRouter, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import Depends
from typing import Any, Optional
from datetime import datetime, timezone
import json
from core.database import get_db
from intelligence.risk_scoring.engine import risk_scoring_engine
from intelligence.risk_scoring.group_scorer import group_scorer
from kinetic.functions.cirp_contagion import assessCIRPContagionRisk
from storage.object_data_funnel import object_data_funnel

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/risk/{object_type}/{primary_key}")
async def get_risk_score(
    object_type: str,
    primary_key: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT properties FROM ontology_objects WHERE object_type = :ot AND primary_key = :pk AND is_deleted = FALSE"),
        {"ot": object_type.lower(), "pk": primary_key},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{object_type}/{primary_key} not found")

    props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    risk_score = props.get("riskScore", 0) or 0
    risk_flags = props.get("riskFlags", [])
    if isinstance(risk_flags, str):
        risk_flags = risk_flags.split(",") if risk_flags else []

    band = "LOW" if risk_score < 40 else ("MEDIUM" if risk_score < 70 else "HIGH")
    return {
        "object_type": object_type,
        "primary_key": primary_key,
        "risk_score": risk_score,
        "risk_band": band,
        "risk_flags": risk_flags,
        "color": {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}[band],
    }


@router.get("/alerts")
async def list_alerts(
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    object_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conditions = ["object_type = 'alert'", "is_deleted = FALSE"]
    params: dict[str, Any] = {}

    if severity:
        conditions.append("properties->>'severity' = :severity")
        params["severity"] = severity
    if alert_type:
        conditions.append("properties->>'alertType' = :alert_type")
        params["alert_type"] = alert_type
    if is_active is not None:
        val = "true" if is_active else "false"
        conditions.append(f"properties->>'isActive' = '{val}'")
    if object_type:
        conditions.append("properties->>'affectedEntityType' = :entity_type")
        params["entity_type"] = object_type

    where_clause = " AND ".join(conditions)
    result = await db.execute(
        text(f"SELECT primary_key, properties FROM ontology_objects WHERE {where_clause} ORDER BY updated_at DESC"),
        params,
    )
    alerts = []
    for row in result.fetchall():
        props = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
        alerts.append({"alertId": row[0], **props})

    return {"total": len(alerts), "alerts": alerts}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_note: str = Query(...),
    actor_id: str = Query(default="compliance_head"),
    actor_role: str = Query(default="compliance_head"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT properties FROM ontology_objects WHERE object_type = 'alert' AND primary_key = :pk"),
        {"pk": alert_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    props["isActive"] = False
    props["resolvedAt"] = datetime.now(timezone.utc).isoformat()
    props["resolvedBy"] = actor_id
    props["resolutionNote"] = resolution_note

    write_result = await object_data_funnel.write_object(
        object_type="alert",
        data=props,
        source="user_api:resolve_alert",
        actor=actor_id,
    )
    return {"success": write_result.success, "alert_id": alert_id}


@router.get("/group-risk/{company_cin}")
async def get_group_risk(company_cin: str) -> dict[str, Any]:
    assessment = await group_scorer.compute_group_risk(company_cin)
    return {
        "parent_cin": assessment.parent_cin,
        "group_score": assessment.group_score,
        "subsidiary_count": assessment.subsidiary_count,
        "highest_risk_entity": assessment.highest_risk_entity,
        "highest_risk_score": assessment.highest_risk_score,
        "has_cirp_subsidiary": assessment.has_cirp_subsidiary,
        "breakdown": assessment.breakdown,
    }


@router.get("/cirp-contagion/{company_cin}")
async def get_cirp_contagion(company_cin: str) -> dict[str, Any]:
    risk_map = await assessCIRPContagionRisk(company_cin)
    return {
        "source_cin": risk_map.source_cin,
        "total_affected": risk_map.total_affected,
        "highest_severity": risk_map.highest_severity,
        "affected_entities": risk_map.affected_entities,
    }


@router.get("/anomalies")
async def list_anomalies(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT properties->>'alertType' AS alert_type, COUNT(*) AS count,
                   json_agg(properties) AS alerts
            FROM ontology_objects
            WHERE object_type = 'alert'
              AND is_deleted = FALSE
              AND properties->>'isActive' = 'true'
            GROUP BY properties->>'alertType'
            ORDER BY count DESC
        """)
    )
    groups = {}
    for row in result.fetchall():
        groups[row[0]] = {"count": row[1], "alerts": row[2]}

    return {"anomaly_groups": groups, "total_active_anomalies": sum(g["count"] for g in groups.values())}
