"""
ObjectDataFunnel — the sole write path for all ontology data.
Nothing else writes to Neo4j, Elasticsearch, PostgreSQL, or Redis directly.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import AsyncSessionLocal
from core.kafka_publisher import get_ontology_publisher
from .event_store import EventStore, OntologyEvent
from .neo4j_store import Neo4jStore
from .elasticsearch_store import ElasticsearchStore
from .cache_store import CacheStore

logger = logging.getLogger(__name__)


@dataclass
class PropertyChange:
    property_name: str
    old_value: Any
    new_value: Any


@dataclass
class WriteResult:
    success: bool
    object_type: str
    object_id: str
    version: int = 1
    changes: list[PropertyChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ObjectDataFunnel:
    """Central write orchestrator — all writes flow through here."""

    def __init__(self) -> None:
        self._event_store = EventStore()
        self._neo4j_store = Neo4jStore()
        self._es_store = ElasticsearchStore()
        self._cache_store = CacheStore()

    async def write_object(
        self,
        object_type: str,
        data: dict[str, Any],
        source: str,
        actor: str,
    ) -> WriteResult:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            try:
                result = await self._write_object_internal(db, object_type, data, source, actor)
                await db.commit()
                return result
            except Exception as e:
                await db.rollback()
                logger.error("Funnel write_object failed for %s: %s", object_type, e)
                return WriteResult(
                    success=False,
                    object_type=object_type,
                    object_id=data.get("primary_key", "unknown"),
                    errors=[str(e)],
                )

    async def _write_object_internal(
        self,
        db: AsyncSession,
        object_type: str,
        data: dict[str, Any],
        source: str,
        actor: str,
    ) -> WriteResult:
        primary_key = self._extract_primary_key(object_type, data)
        data_hash = self._compute_hash(data)

        # Check existing state
        existing = await self._get_existing(db, object_type, primary_key)
        is_new = existing is None

        if not is_new:
            existing_hash = existing.get("data_hash", "")
            if existing_hash == data_hash:
                return WriteResult(
                    success=True,
                    object_type=object_type,
                    object_id=primary_key,
                    version=existing.get("version", 1),
                    changes=[],
                )

        # Compute diff
        old_props = {} if is_new else (existing.get("properties") or {})
        changes = self._compute_diff(old_props, data)
        new_version = 1 if is_new else (existing.get("version", 1) + 1)

        # 1. Write to PostgreSQL (primary, authoritative)
        await self._write_postgres(db, object_type, primary_key, data, data_hash, new_version)

        # 2. Emit events to event store
        if is_new:
            await self._event_store.emit(db, OntologyEvent(
                object_type=object_type,
                object_id=primary_key,
                event_type="OBJECT_CREATED",
                actor_id=actor,
                source=source,
                new_value=data,
            ))
        else:
            for change in changes:
                await self._event_store.emit(db, OntologyEvent(
                    object_type=object_type,
                    object_id=primary_key,
                    event_type="PROPERTY_CHANGED" if change.property_name != "status" else "STATUS_CHANGED",
                    actor_id=actor,
                    source=source,
                    property_name=change.property_name,
                    old_value=change.old_value,
                    new_value=change.new_value,
                ))

        # 3. Write to Neo4j (graph)
        try:
            await self._neo4j_store.upsert_node(object_type, primary_key, data)
        except Exception as e:
            logger.error("Neo4j write failed for %s/%s: %s", object_type, primary_key, e)

        # 4. Write to Elasticsearch
        try:
            await self._es_store.index_object(object_type, primary_key, data)
        except Exception as e:
            logger.error("ES write failed for %s/%s: %s", object_type, primary_key, e)

        # 5. Invalidate Redis cache
        try:
            await self._cache_store.invalidate(object_type, primary_key)
        except Exception as e:
            logger.warning("Cache invalidation failed for %s/%s: %s", object_type, primary_key, e)

        # 6. Publish to Kafka layer3.ontology.changes (fire-and-forget for L4 cache invalidation)
        get_ontology_publisher().emit_change(
            event_type="OBJECT_CREATED" if is_new else "PROPERTY_CHANGED",
            object_type=object_type,
            object_id=primary_key,
            changed_fields=[c.property_name for c in changes],
        )

        return WriteResult(
            success=True,
            object_type=object_type,
            object_id=primary_key,
            version=new_version,
            changes=changes,
        )

    async def write_link(
        self,
        link_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any],
        actor: str,
        is_inferred: bool = False,
    ) -> WriteResult:
        async with AsyncSessionLocal() as db:
            try:
                await self._write_link_postgres(
                    db, link_type, source_type, source_id, target_type, target_id, properties, is_inferred
                )
                await self._event_store.emit(db, OntologyEvent(
                    object_type=source_type,
                    object_id=source_id,
                    event_type="LINK_CREATED",
                    actor_id=actor,
                    source="funnel",
                    metadata={
                        "link_type": link_type,
                        "target_type": target_type,
                        "target_id": target_id,
                        "properties": properties,
                    },
                ))
                await db.commit()

                # Write to Neo4j
                try:
                    await self._neo4j_store.upsert_relationship(
                        link_type, source_type, source_id, target_type, target_id, properties
                    )
                except Exception as e:
                    logger.error("Neo4j link write failed: %s", e)

                return WriteResult(
                    success=True,
                    object_type=link_type,
                    object_id=f"{source_id}->{target_id}",
                )
            except Exception as e:
                await db.rollback()
                logger.error("Funnel write_link failed: %s", e)
                return WriteResult(
                    success=False,
                    object_type=link_type,
                    object_id=f"{source_id}->{target_id}",
                    errors=[str(e)],
                )

    async def delete_object(
        self,
        object_type: str,
        primary_key: str,
        actor: str,
        reason: str,
    ) -> WriteResult:
        """Soft delete — sets is_deleted=True, never hard deletes."""
        async with AsyncSessionLocal() as db:
            try:
                await db.execute(
                    text("""
                        UPDATE ontology_objects
                        SET is_deleted = TRUE, updated_at = NOW()
                        WHERE object_type = :object_type AND primary_key = :primary_key
                    """),
                    {"object_type": object_type, "primary_key": primary_key},
                )
                await self._event_store.emit(db, OntologyEvent(
                    object_type=object_type,
                    object_id=primary_key,
                    event_type="OBJECT_DELETED",
                    actor_id=actor,
                    source="user_action",
                    metadata={"reason": reason},
                ))
                await db.commit()
                await self._cache_store.invalidate(object_type, primary_key)
                return WriteResult(success=True, object_type=object_type, object_id=primary_key)
            except Exception as e:
                await db.rollback()
                return WriteResult(success=False, object_type=object_type, object_id=primary_key, errors=[str(e)])

    async def _get_existing(
        self, db: AsyncSession, object_type: str, primary_key: str
    ) -> Optional[dict]:
        result = await db.execute(
            text("""
                SELECT properties, data_hash, version
                FROM ontology_objects
                WHERE object_type = :object_type AND primary_key = :primary_key
                  AND is_deleted = FALSE
            """),
            {"object_type": object_type, "primary_key": primary_key},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def _write_postgres(
        self,
        db: AsyncSession,
        object_type: str,
        primary_key: str,
        data: dict,
        data_hash: str,
        version: int,
    ) -> None:
        props_json = json.dumps(data, default=str)
        await db.execute(
            text("""
                INSERT INTO ontology_objects (object_type, primary_key, properties, data_hash, version, updated_at)
                VALUES (:object_type, :primary_key, :properties::jsonb, :data_hash, :version, NOW())
                ON CONFLICT (object_type, primary_key) DO UPDATE
                SET properties = :properties::jsonb,
                    data_hash = :data_hash,
                    version = :version,
                    updated_at = NOW(),
                    is_deleted = FALSE
            """),
            {
                "object_type": object_type,
                "primary_key": primary_key,
                "properties": props_json,
                "data_hash": data_hash,
                "version": version,
            },
        )

    async def _write_link_postgres(
        self,
        db: AsyncSession,
        link_type: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        properties: dict,
        is_inferred: bool,
    ) -> None:
        props_json = json.dumps(properties, default=str)
        inferred_by = properties.get("inferredBy")
        confidence = properties.get("inferenceConfidence")
        await db.execute(
            text("""
                INSERT INTO ontology_links
                    (link_type, source_type, source_id, target_type, target_id,
                     properties, is_inferred, inferred_by, inference_confidence, updated_at)
                VALUES
                    (:link_type, :source_type, :source_id, :target_type, :target_id,
                     :properties::jsonb, :is_inferred, :inferred_by, :confidence, NOW())
                ON CONFLICT DO NOTHING
            """),
            {
                "link_type": link_type,
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "properties": props_json,
                "is_inferred": is_inferred,
                "inferred_by": inferred_by,
                "confidence": confidence,
            },
        )

    @staticmethod
    def _extract_primary_key(object_type: str, data: dict) -> str:
        pk_fields = {
            "company": "cin",
            "director": "din",
            "project": "projectId",
            "regulatory_action": "actionId",
            "legal_case": "caseId",
            "insolvency_proceeding": "cirpId",
            "address": "normalizedAddress",
            "regulatory_body": "bodyId",
            "government_entity": "entityId",
            "event": "eventId",
            "alert": "alertId",
        }
        pk_field = pk_fields.get(object_type.lower(), "id")
        pk_value = data.get(pk_field) or data.get("primary_key") or data.get("id", "")
        return str(pk_value)

    @staticmethod
    def _compute_hash(data: dict) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _compute_diff(old: dict, new: dict) -> list[PropertyChange]:
        changes: list[PropertyChange] = []
        all_keys = set(old) | set(new)
        skip_keys = {"lastUpdated", "dataQualityScore", "riskScore"}
        for key in all_keys:
            if key in skip_keys:
                continue
            old_val = old.get(key)
            new_val = new.get(key)
            if str(old_val) != str(new_val):
                changes.append(PropertyChange(
                    property_name=key,
                    old_value=old_val,
                    new_value=new_val,
                ))
        return changes


object_data_funnel = ObjectDataFunnel()
