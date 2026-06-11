import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kinetic.workflow_engine import WorkflowEngine


class TestWorkflowEngine:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_has_permission_analyst_above_restricted(self):
        assert self.engine._has_permission("analyst", "restricted_viewer") is True

    def test_has_permission_restricted_below_analyst(self):
        assert self.engine._has_permission("restricted_viewer", "analyst") is False

    def test_has_permission_platform_admin_all(self):
        assert self.engine._has_permission("platform_administrator", "compliance_head") is True

    def test_unknown_action_type(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.engine.execute_action("NonExistentAction", {}, "user1", "analyst")
        )
        assert result.success is False
        assert "Unknown action type" in result.errors[0]

    def test_list_action_types_returns_all(self):
        types = self.engine.list_action_types()
        names = [t["name"] for t in types]
        assert "FlagCompanyForReview" in names
        assert "UpdateProjectStatus" in names
        assert "MarkRegulatoryActionResolved" in names
