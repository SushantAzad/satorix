"""
Report Aggregator — orchestrates report generation via Layer 5,
with caching in the l6_report_cache table.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)

# Valid report types
REPORT_TYPES = {
    "corporate_due_diligence",
    "regulatory_exposure",
    "portfolio_health",
    "peer_comparison",
}

_POLL_INTERVAL_S = 3.0
_POLL_TIMEOUT_S = 120.0


# ---------------------------------------------------------------------------
# Cache helpers (using SQLAlchemy text queries to avoid circular imports)
# ---------------------------------------------------------------------------

async def _get_cached_report(
    db: AsyncSession, user_id: str, entity_type: str, entity_id: str, report_type: str
) -> Optional[Dict]:
    from sqlalchemy.sql import text
    try:
        result = await db.execute(
            text(
                """
                SELECT id, report_content, generated_at, expires_at
                FROM l6_report_cache
                WHERE user_id = :user_id
                  AND entity_type = :entity_type
                  AND entity_id = :entity_id
                  AND report_type = :report_type
                  AND expires_at > NOW()
                ORDER BY generated_at DESC
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "report_type": report_type,
            },
        )
        row = result.fetchone()
        if row:
            return {
                "report_id": str(row.id),
                "status": "completed",
                "report_content": row.report_content,
                "generated_at": row.generated_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
                "cached": True,
            }
    except Exception as exc:
        logger.warning("_get_cached_report failed: %s", exc)
    return None


async def _save_report_cache(
    db: AsyncSession,
    user_id: str,
    entity_type: str,
    entity_id: str,
    report_type: str,
    report_content: Dict,
) -> str:
    from sqlalchemy.sql import text
    report_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    try:
        await db.execute(
            text(
                """
                INSERT INTO l6_report_cache
                    (id, user_id, entity_type, entity_id, report_type,
                     report_content, generated_at, expires_at)
                VALUES
                    (:id, :user_id, :entity_type, :entity_id, :report_type,
                     :report_content::jsonb, NOW(), :expires_at)
                """
            ),
            {
                "id": report_id,
                "user_id": user_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "report_type": report_type,
                "report_content": __import__("json").dumps(report_content),
                "expires_at": expires_at,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("_save_report_cache failed: %s", exc)
        await db.rollback()
    return report_id


async def _delete_report(db: AsyncSession, report_id: str, user_id: str) -> bool:
    from sqlalchemy.sql import text
    try:
        result = await db.execute(
            text(
                "DELETE FROM l6_report_cache WHERE id = :id AND user_id = :user_id"
            ),
            {"id": report_id, "user_id": user_id},
        )
        await db.commit()
        return result.rowcount > 0
    except Exception as exc:
        logger.warning("_delete_report failed: %s", exc)
        await db.rollback()
        return False


async def _list_user_reports(db: AsyncSession, user_id: str) -> List[Dict]:
    from sqlalchemy.sql import text
    try:
        result = await db.execute(
            text(
                """
                SELECT id, entity_type, entity_id, report_type, generated_at, expires_at
                FROM l6_report_cache
                WHERE user_id = :user_id AND expires_at > NOW()
                ORDER BY generated_at DESC
                LIMIT 50
                """
            ),
            {"user_id": user_id},
        )
        rows = result.fetchall()
        return [
            {
                "report_id": str(r.id),
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "report_type": r.report_type,
                "generated_at": r.generated_at.isoformat(),
                "expires_at": r.expires_at.isoformat(),
                "status": "completed",
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("_list_user_reports failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

async def generate_report(
    clients: LayerClients,
    db: AsyncSession,
    user_id: str,
    entity_type: str,
    entity_id: str,
    report_type: str,
    depth: int = 2,
) -> Dict:
    """
    Check cache first; if miss, trigger Layer 5 report generation.
    Returns immediately with {report_id, status: "pending"} or cached result.
    """
    if report_type not in REPORT_TYPES:
        return {
            "error": f"Unknown report_type '{report_type}'. Valid: {sorted(REPORT_TYPES)}"
        }

    # Cache hit
    cached = await _get_cached_report(db, user_id, entity_type, entity_id, report_type)
    if cached:
        logger.info("Report cache hit for %s/%s type=%s", entity_type, entity_id, report_type)
        return cached

    # Trigger L5 generation
    gen_result = await clients.generate_report(entity_type, entity_id, report_type)
    if gen_result is None:
        return {
            "report_id": None,
            "status": "failed",
            "error": "Layer 5 report service unavailable.",
        }

    report_id = gen_result.get("report_id") or gen_result.get("id")
    status = gen_result.get("status", "pending")

    return {
        "report_id": report_id,
        "status": status,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "report_type": report_type,
    }


async def poll_report(
    clients: LayerClients,
    db: AsyncSession,
    user_id: str,
    report_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    report_type: Optional[str] = None,
) -> Dict:
    """
    Check report status from Layer 5; save to cache when completed.
    """
    result = await clients.get_report_status(report_id)
    if result is None:
        return {"report_id": report_id, "status": "unknown"}

    if result.get("status") == "completed" and entity_type and entity_id and report_type:
        content = result.get("content") or result.get("report") or result
        saved_id = await _save_report_cache(
            db, user_id, entity_type, entity_id, report_type, content
        )
        return {
            "report_id": saved_id,
            "status": "completed",
            "report_content": content,
            "cached": True,
        }

    return result
