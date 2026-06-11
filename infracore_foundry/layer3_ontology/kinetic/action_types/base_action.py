from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone
import uuid
import logging
from dynamic.audit_logger import audit_logger

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class ActionResult:
    success: bool
    action_type: str
    action_id: str
    changes: list[dict] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    executed_at: str = ""

    def __post_init__(self) -> None:
        if not self.executed_at:
            self.executed_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ActionContext:
    actor_id: str
    actor_role: str
    parameters: dict[str, Any]
    session_id: Optional[str] = None
    ip_address: Optional[str] = None


class BaseAction(ABC):
    action_name: str = ""
    required_role: str = "analyst"
    requires_approval: bool = False

    @abstractmethod
    async def validate(self, context: ActionContext) -> ValidationResult:
        pass

    @abstractmethod
    async def execute(self, context: ActionContext) -> ActionResult:
        pass

    async def on_success(self, context: ActionContext, result: ActionResult) -> None:
        pass

    async def run(self, context: ActionContext) -> ActionResult:
        action_id = str(uuid.uuid4())
        validation = await self.validate(context)
        if not validation.valid:
            return ActionResult(
                success=False,
                action_type=self.action_name,
                action_id=action_id,
                errors=validation.errors,
            )

        result = await self.execute(context)
        result.action_id = action_id

        await audit_logger.log_action(
            actor_id=context.actor_id,
            actor_role=context.actor_role,
            action_type=self.action_name,
            parameters=context.parameters,
            result={"success": result.success, "changes": result.changes},
            success=result.success,
            session_id=context.session_id,
            ip_address=context.ip_address,
        )

        if result.success:
            await self.on_success(context, result)

        return result
