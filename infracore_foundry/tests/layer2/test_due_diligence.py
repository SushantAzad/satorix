"""Regression tests for the dashboard due-diligence workflow."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "report_under_test", ROOT / "layer6_dashboard/backend/aggregators/report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class DueDiligenceTests(unittest.IsolatedAsyncioTestCase):
    def clients(self, score):
        return SimpleNamespace(
            get_entity=AsyncMock(return_value={"name": "Synthetic company", "synthetic": True}),
            get_network=AsyncMock(return_value={"nodes": [], "edges": []}),
            get_risk_score=AsyncMock(return_value={
                "risk_score": score, "risk_band": "NONE" if score is None else "HIGH"}),
        )

    async def test_scores_and_tenant_forwarding(self):
        for score in (0, 100, None):
            clients = self.clients(score)
            with patch.object(report, "_save_report_cache", AsyncMock(return_value="saved")) as save:
                with patch.object(report, "poll_report", AsyncMock(return_value={"status": "completed"})):
                    await report.generate_report(clients, None, "user", "company", "TEST",
                                                 "corporate_due_diligence", client_id="tenant")
                content = save.call_args.args[-1]
                self.assertEqual(content["sections"]["executive_summary"]["risk_score"], score)
                self.assertTrue(content["synthetic"])
                self.assertEqual(content["coverage"], "partial")
                self.assertEqual(content["sections"]["relationship_exposure"]["status"], "available")
                clients.get_entity.assert_awaited_once_with("company", "TEST", client_id="tenant")
                clients.get_network.assert_awaited_once_with("company", "TEST", depth=2, client_id="tenant")

    async def test_missing_entity_never_saved(self):
        clients = self.clients(0)
        clients.get_entity.return_value = None
        with patch.object(report, "_save_report_cache", AsyncMock()) as save:
            with self.assertRaises(LookupError):
                await report.generate_report(clients, None, "user", "company", "missing",
                                             "corporate_due_diligence", client_id="tenant")
            save.assert_not_awaited()

    async def test_unavailable_network_is_explicit(self):
        clients = self.clients(None)
        clients.get_network.return_value = None
        with patch.object(report, "_save_report_cache", AsyncMock(return_value="saved")) as save:
            with patch.object(report, "poll_report", AsyncMock()):
                await report.generate_report(clients, None, "user", "company", "TEST",
                                             "corporate_due_diligence", client_id="tenant")
            content = save.call_args.args[-1]
            self.assertEqual(content["sections"]["relationship_snapshot"]["status"], "unavailable")

    async def test_failed_save_raises_and_rolls_back(self):
        db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("database offline")),
                             rollback=AsyncMock(), commit=AsyncMock())
        with self.assertRaises(RuntimeError):
            await report._save_report_cache(db, "user", "company", "TEST", "corporate_due_diligence", {})
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_read_is_owner_and_tenant_scoped_without_upstream_fallback(self):
        clients = SimpleNamespace(get_report_status=AsyncMock())
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(fetchone=lambda: None)))
        result = await report.poll_report(clients, db, "owner", "report", "tenant")
        self.assertEqual(result["status"], "unknown")
        sql, params = db.execute.call_args.args
        self.assertIn("user_id = :user_id", str(sql))
        self.assertIn("report_content->>'client_id' = :client_id", str(sql))
        self.assertEqual(params["user_id"], "owner")
        clients.get_report_status.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
