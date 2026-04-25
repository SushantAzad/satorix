from typing import Any
import logging
from .action_types.base_action import ActionContext, ActionResult, BaseAction
from .action_types.flag_for_review import FlagCompanyForReview
from .action_types.update_project_status import UpdateProjectStatus
from .action_types.mark_regulatory_resolved import MarkRegulatoryActionResolved
from .action_types.create_alert import CreateIntelligenceAlert
from .action_types.merge_objects import MergeCompanyObjects

logger = logging.getLogger(__name__)

ACTION_REGISTRY: dict[str, type[BaseAction]] = {
    "FlagCompanyForReview": FlagCompanyForReview,
    "UpdateProjectStatus": UpdateProjectStatus,
    "MarkRegulatoryActionResolved": MarkRegulatoryActionResolved,
    "CreateIntelligenceAlert": CreateIntelligenceAlert,
    "MergeCompanyObjects": MergeCompanyObjects,
}


class WorkflowEngine:
    async def execute_action(
        self,
        action_type_name: str,
        parameters: dict[str, Any],
        actor_id: str,
        actor_role: str,
        session_id: str | None = None,
        ip_address: str | None = None,
    ) -> ActionResult:
        action_class = ACTION_REGISTRY.get(action_type_name)
        if not action_class:
            return ActionResult(
                success=False,
                action_type=action_type_name,
                action_id="",
                errors=[f"Unknown action type: {action_type_name}"],
            )

        action = action_class()

        # Role check
        if not self._has_permission(actor_role, action.required_role):
            return ActionResult(
                success=False,
                action_type=action_type_name,
                action_id="",
                errors=[f"Insufficient permissions. Required: {action.required_role}, got: {actor_role}"],
            )

        context = ActionContext(
            actor_id=actor_id,
            actor_role=actor_role,
            parameters=parameters,
            session_id=session_id,
            ip_address=ip_address,
        )
        return await action.run(context)

    def _has_permission(self, actor_role: str, required_role: str) -> bool:
        role_hierarchy = [
            "restricted_viewer", "analyst", "operations_team",
            "compliance_head", "data_steward", "ontology_designer",
            "platform_administrator", "system",
        ]
        try:
            actor_level = role_hierarchy.index(actor_role.lower())
            required_level = role_hierarchy.index(required_role.lower())
            return actor_level >= required_level
        except ValueError:
            return actor_role.lower() in ("platform_administrator", "system")

    def list_action_types(self) -> list[dict]:
        return [
            {
                "name": name,
                "required_role": cls.required_role,
                "requires_approval": cls.requires_approval,
            }
            for name, cls in ACTION_REGISTRY.items()
        ]


workflow_engine = WorkflowEngine()
