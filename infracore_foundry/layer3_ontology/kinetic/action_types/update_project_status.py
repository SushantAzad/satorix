from .base_action import BaseAction, ActionContext, ActionResult, ValidationResult
from storage.object_data_funnel import object_data_funnel
from core.database import AsyncSessionLocal
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)

VALID_STATUSES = {"Operational", "Under Construction", "Stressed", "Cancelled"}


class UpdateProjectStatus(BaseAction):
    action_name = "UpdateProjectStatus"
    required_role = "operations_team"
    requires_approval = False

    async def validate(self, context: ActionContext) -> ValidationResult:
        project_id = context.parameters.get("projectId")
        new_status = context.parameters.get("status")

        if not project_id:
            return ValidationResult(valid=False, errors=["projectId is required"])
        if new_status not in VALID_STATUSES:
            return ValidationResult(valid=False, errors=[f"Invalid status. Must be one of: {VALID_STATUSES}"])

        if new_status == "Operational":
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("SELECT properties->>'actualCompletionDate' FROM ontology_objects WHERE object_type = 'project' AND primary_key = :pk"),
                    {"pk": project_id},
                )
                row = result.first()
                if row and not row[0]:
                    return ValidationResult(valid=False, errors=["Cannot set Operational without actualCompletionDate"])

        return ValidationResult(valid=True)

    async def execute(self, context: ActionContext) -> ActionResult:
        project_id = context.parameters["projectId"]
        new_status = context.parameters["status"]

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT properties FROM ontology_objects WHERE object_type = 'project' AND primary_key = :pk"),
                {"pk": project_id},
            )
            row = result.first()
            props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")

        old_status = props.get("status")
        props["status"] = new_status

        write_result = await object_data_funnel.write_object(
            object_type="project",
            data=props,
            source="action:UpdateProjectStatus",
            actor=context.actor_id,
        )

        side_effects = []
        if new_status == "Stressed" and write_result.success:
            side_effects.append("Triggered group risk recompute for parent company")

        return ActionResult(
            success=write_result.success,
            action_type=self.action_name,
            action_id="",
            changes=[{"field": "status", "old_value": old_status, "new_value": new_status}],
            side_effects=side_effects,
            errors=write_result.errors,
        )
