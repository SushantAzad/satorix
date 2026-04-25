from datetime import datetime, timezone
from .base_action import BaseAction, ActionContext, ActionResult, ValidationResult
from storage.object_data_funnel import object_data_funnel
import logging

logger = logging.getLogger(__name__)


class CreateIntelligenceAlert(BaseAction):
    action_name = "CreateIntelligenceAlert"
    required_role = "system"
    requires_approval = False

    async def validate(self, context: ActionContext) -> ValidationResult:
        required = ["alertId", "severity", "alertType", "title", "message"]
        for f in required:
            if not context.parameters.get(f):
                return ValidationResult(valid=False, errors=[f"Field {f} is required"])
        return ValidationResult(valid=True)

    async def execute(self, context: ActionContext) -> ActionResult:
        alert_data = {
            **context.parameters,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "isActive": True,
        }
        write_result = await object_data_funnel.write_object(
            object_type="alert",
            data=alert_data,
            source="action:CreateIntelligenceAlert",
            actor=context.actor_id,
        )
        return ActionResult(
            success=write_result.success,
            action_type=self.action_name,
            action_id="",
            changes=[{"created": "alert", "alertId": context.parameters.get("alertId")}],
            errors=write_result.errors,
        )
