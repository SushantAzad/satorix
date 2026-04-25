import uuid
import json
from datetime import datetime, timezone
from typing import Any, Optional
import logging
from core.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AuditLogger:
    """Immutable audit logger. Write-only from application code."""

    async def log(
        self,
        actor_id: str,
        actor_role: str,
        action_type: str,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        properties_accessed: Optional[list[str]] = None,
        old_value: Any = None,
        new_value: Any = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO ontology_audit_log
                            (id, timestamp, actor_id, actor_role, action_type,
                             object_type, object_id, properties_accessed,
                             old_value, new_value, ip_address, session_id,
                             success, error_message)
                        VALUES
                            (:id, :ts, :actor_id, :actor_role, :action_type,
                             :object_type, :object_id, :properties_accessed::jsonb,
                             :old_value::jsonb, :new_value::jsonb,
                             :ip_address, :session_id, :success, :error_message)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "ts": datetime.now(timezone.utc),
                        "actor_id": actor_id,
                        "actor_role": actor_role,
                        "action_type": action_type,
                        "object_type": object_type,
                        "object_id": object_id,
                        "properties_accessed": json.dumps(properties_accessed),
                        "old_value": json.dumps(old_value, default=str) if old_value else None,
                        "new_value": json.dumps(new_value, default=str) if new_value else None,
                        "ip_address": ip_address,
                        "session_id": session_id,
                        "success": success,
                        "error_message": error_message,
                    },
                )
                await db.commit()
        except Exception as e:
            logger.error("CRITICAL: Audit log write failed: %s", e)

    async def log_read(self, actor_id: str, actor_role: str, object_type: str, object_id: str, properties: list[str], **kwargs: Any) -> None:
        await self.log(actor_id=actor_id, actor_role=actor_role, action_type="READ_OBJECT",
                       object_type=object_type, object_id=object_id, properties_accessed=properties, **kwargs)

    async def log_write(self, actor_id: str, actor_role: str, object_type: str, object_id: str, old_value: Any, new_value: Any, **kwargs: Any) -> None:
        await self.log(actor_id=actor_id, actor_role=actor_role, action_type="WRITE_OBJECT",
                       object_type=object_type, object_id=object_id, old_value=old_value, new_value=new_value, **kwargs)

    async def log_action(self, actor_id: str, actor_role: str, action_type: str, parameters: dict, result: dict, **kwargs: Any) -> None:
        await self.log(actor_id=actor_id, actor_role=actor_role, action_type=f"EXECUTE_ACTION:{action_type}",
                       new_value={"parameters": parameters, "result": result}, **kwargs)


audit_logger = AuditLogger()
