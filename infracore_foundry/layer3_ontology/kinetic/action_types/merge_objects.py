from .base_action import BaseAction, ActionContext, ActionResult, ValidationResult
from storage.object_data_funnel import object_data_funnel
from core.database import AsyncSessionLocal
from core.neo4j_client import neo4j_client
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)


class MergeCompanyObjects(BaseAction):
    action_name = "MergeCompanyObjects"
    required_role = "data_steward"
    requires_approval = True

    async def validate(self, context: ActionContext) -> ValidationResult:
        survivor_cin = context.parameters.get("survivorCIN")
        duplicate_cin = context.parameters.get("duplicateCIN")
        approval_token = context.parameters.get("approvalToken")

        if not survivor_cin or not duplicate_cin:
            return ValidationResult(valid=False, errors=["survivorCIN and duplicateCIN are required"])
        if not approval_token:
            return ValidationResult(valid=False, errors=["approvalToken required (two-person authorization)"])
        if survivor_cin == duplicate_cin:
            return ValidationResult(valid=False, errors=["Survivor and duplicate cannot be the same CIN"])

        async with AsyncSessionLocal() as db:
            for cin in [survivor_cin, duplicate_cin]:
                result = await db.execute(
                    text("SELECT properties->>'duplicate_candidate' FROM ontology_objects WHERE object_type = 'company' AND primary_key = :pk"),
                    {"pk": cin},
                )
                row = result.first()
                if not row:
                    return ValidationResult(valid=False, errors=[f"Company {cin} not found"])

        return ValidationResult(valid=True)

    async def execute(self, context: ActionContext) -> ActionResult:
        survivor_cin = context.parameters["survivorCIN"]
        duplicate_cin = context.parameters["duplicateCIN"]

        # Transfer all Neo4j relationships from duplicate to survivor
        try:
            await neo4j_client.run_write(
                """
                MATCH (duplicate:Company {cin: $dup}), (survivor:Company {cin: $surv})
                CALL apoc.refactor.mergeNodes([duplicate, survivor], {properties: 'overwrite', mergeRels: true})
                YIELD node RETURN node
                """,
                {"dup": duplicate_cin, "surv": survivor_cin},
            )
        except Exception as e:
            logger.warning("Neo4j APOC merge failed (APOC may not be available): %s", e)
            # Fall back: manually transfer relationships
            await neo4j_client.run_write(
                """
                MATCH (dup:Company {cin: $dup})-[r]->(n)
                MATCH (surv:Company {cin: $surv})
                CALL apoc.create.relationship(surv, type(r), properties(r), n) YIELD rel
                DELETE r
                """,
                {"dup": duplicate_cin, "surv": survivor_cin},
            )

        # Soft-delete the duplicate in PostgreSQL
        await object_data_funnel.delete_object(
            object_type="company",
            primary_key=duplicate_cin,
            actor=context.actor_id,
            reason=f"Merged into {survivor_cin} — duplicate",
        )

        return ActionResult(
            success=True,
            action_type=self.action_name,
            action_id="",
            changes=[
                {"action": "merged", "duplicate": duplicate_cin, "survivor": survivor_cin}
            ],
            side_effects=[f"All relationships from {duplicate_cin} transferred to {survivor_cin}"],
        )
