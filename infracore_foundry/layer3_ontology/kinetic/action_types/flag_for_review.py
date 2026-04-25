from datetime import datetime, timezone
from .base_action import BaseAction, ActionContext, ActionResult, ValidationResult
from storage.object_data_funnel import object_data_funnel
from core.database import AsyncSessionLocal
from sqlalchemy import text
import uuid
import logging

logger = logging.getLogger(__name__)


class FlagCompanyForReview(BaseAction):
    action_name = "FlagCompanyForReview"
    required_role = "analyst"
    requires_approval = False

    async def validate(self, context: ActionContext) -> ValidationResult:
        cin = context.parameters.get("cin")
        if not cin:
            return ValidationResult(valid=False, errors=["CIN is required"])

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT properties->>'status' FROM ontology_objects WHERE object_type = 'company' AND primary_key = :pk AND is_deleted = FALSE"),
                {"pk": cin},
            )
            row = result.first()
            if not row:
                return ValidationResult(valid=False, errors=[f"Company {cin} not found"])
            if row[0] == "Archived":
                return ValidationResult(valid=False, errors=["Cannot flag archived company"])

        return ValidationResult(valid=True)

    async def execute(self, context: ActionContext) -> ActionResult:
        cin = context.parameters["cin"]
        reason = context.parameters.get("reason", "Flagged for review")

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT properties FROM ontology_objects WHERE object_type = 'company' AND primary_key = :pk"),
                {"pk": cin},
            )
            row = result.first()
            import json
            props = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")

        props["reviewFlag"] = True
        props["reviewReason"] = reason
        props["reviewedBy"] = context.actor_id
        props["reviewedAt"] = datetime.now(timezone.utc).isoformat()

        write_result = await object_data_funnel.write_object(
            object_type="company",
            data=props,
            source="action:FlagCompanyForReview",
            actor=context.actor_id,
        )

        return ActionResult(
            success=write_result.success,
            action_type=self.action_name,
            action_id="",
            changes=[{"field": "reviewFlag", "new_value": True}],
            errors=write_result.errors,
        )

    async def on_success(self, context: ActionContext, result: ActionResult) -> None:
        cin = context.parameters["cin"]
        alert_id = f"REVIEW-{cin}-{str(uuid.uuid4())[:8]}"
        await object_data_funnel.write_object(
            object_type="alert",
            data={
                "alertId": alert_id,
                "severity": "MEDIUM",
                "alertType": "ONGOING_REGULATORY",
                "title": f"Company Flagged for Review",
                "message": f"Company {cin} was flagged for review by {context.actor_id}: {context.parameters.get('reason', '')}",
                "affectedEntityType": "company",
                "affectedEntityId": cin,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "isActive": True,
            },
            source="action:FlagCompanyForReview:side_effect",
            actor="system",
        )
