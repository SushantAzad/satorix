import uuid
import json
from typing import Any, Optional
from datetime import datetime, timezone
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ObjectSetService:
    async def create_static_set(
        self,
        db: AsyncSession,
        name: str,
        description: str,
        object_type: str,
        members: list[str],
        created_by: str,
    ) -> str:
        set_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO ontology_object_sets
                    (id, name, description, set_type, object_type, static_members, created_by)
                VALUES (:id, :name, :desc, 'static', :ot, CAST(:members AS jsonb), :created_by)
            """),
            {
                "id": set_id, "name": name, "desc": description,
                "ot": object_type, "members": json.dumps(members), "created_by": created_by,
            },
        )
        await db.commit()
        return set_id

    async def create_dynamic_set(
        self,
        db: AsyncSession,
        name: str,
        description: str,
        object_type: str,
        filter_definition: dict[str, Any],
        created_by: str,
    ) -> str:
        set_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO ontology_object_sets
                    (id, name, description, set_type, object_type, filter_definition, created_by)
                VALUES (:id, :name, :desc, 'dynamic', :ot, CAST(:filter_def AS jsonb), :created_by)
            """),
            {
                "id": set_id, "name": name, "desc": description,
                "ot": object_type,
                "filter_def": json.dumps(filter_definition),
                "created_by": created_by,
            },
        )
        await db.commit()
        return set_id

    async def evaluate_dynamic_set(
        self,
        db: AsyncSession,
        set_id: str,
    ) -> list[str]:
        result = await db.execute(
            text("SELECT object_type, filter_definition FROM ontology_object_sets WHERE id = :id AND set_type = 'dynamic'"),
            {"id": set_id},
        )
        row = result.first()
        if not row:
            return []

        object_type, filter_def = row[0], row[1]
        filters = filter_def if isinstance(filter_def, dict) else json.loads(filter_def)

        # Build dynamic query from filter definition
        conditions = ["object_type = :ot", "is_deleted = FALSE"]
        params: dict = {"ot": object_type}

        for field, value in filters.items():
            if field == "riskScore_min":
                conditions.append(f"(properties->>'riskScore')::int >= :rs_min")
                params["rs_min"] = value
            elif field == "riskScore_max":
                conditions.append(f"(properties->>'riskScore')::int <= :rs_max")
                params["rs_max"] = value
            elif field == "status":
                conditions.append("properties->>'status' = :status")
                params["status"] = value

        where_clause = " AND ".join(conditions)
        members_result = await db.execute(
            text(f"SELECT primary_key FROM ontology_objects WHERE {where_clause}"),
            params,
        )
        return [row[0] for row in members_result.fetchall()]

    async def get_set(self, db: AsyncSession, set_id: str) -> Optional[dict]:
        result = await db.execute(
            text("SELECT * FROM ontology_object_sets WHERE id = :id"),
            {"id": set_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_sets(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(
            text("SELECT * FROM ontology_object_sets WHERE is_active = TRUE ORDER BY created_at DESC")
        )
        return [dict(row) for row in result.mappings().all()]


object_set_service = ObjectSetService()
