from datetime import date
from .base_action import BaseAction, ActionContext, ActionResult, ValidationResult
from storage.object_data_funnel import object_data_funnel
from core.database import AsyncSessionLocal
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)


class MarkRegulatoryActionResolved(BaseAction):
    action_name = "MarkRegulatoryActionResolved"
    required_role = "compliance_head"
    requires_approval = False

    async def validate(self, context: ActionContext) -> ValidationResult:
        action_id = context.parameters.get("actionId")
        resolution_desc = context.parameters.get("resolutionDescription")
        if not action_id:
            return ValidationResult(valid=False, errors=["actionId is required"])
        if not resolution_desc:
            return ValidationResult(valid=False, errors=["resolutionDescription is required"])
        return ValidationResult(valid=True)

    async def execute(self, context: ActionContext) -> ActionResult:
        action_id = context.parameters["actionId"]
        resolution_desc = context.parameters["resolutionDescription"]

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT properties FROM ontology_objects WHERE object_type = 'regulatory_action' AND primary_key = :pk"),
                {"pk": action_id},
            )
            row = result.first()
            if not row:
                return ActionResult(success=False, action_type=self.action_name, action_id="", errors=["Action not found"])
            props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")

        props["status"] = "Resolved"
        props["resolutionDate"] = str(date.today())
        props["resolutionDescription"] = resolution_desc

        write_result = await object_data_funnel.write_object(
            object_type="regulatory_action",
            data=props,
            source="action:MarkRegulatoryActionResolved",
            actor=context.actor_id,
        )

        return ActionResult(
            success=write_result.success,
            action_type=self.action_name,
            action_id="",
            changes=[{"field": "status", "new_value": "Resolved"}],
            side_effects=["Risk scores recomputed for affected companies"],
            errors=write_result.errors,
        )
