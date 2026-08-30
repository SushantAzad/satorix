import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import HTTPException
from api.routes import focused_alerts


class AlertRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_tenant_is_not_global_fallback(self):
        for user in ({}, {'client_id': 'PLATFORM_GLOBAL'}):
            with self.assertRaises(HTTPException) as caught:
                await focused_alerts.state(AsyncMock(), user)
            self.assertEqual(caught.exception.status_code, 403)

    async def test_read_query_filters_tenant(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
        self.assertIsNone(await focused_alerts.state(db, {'client_id': 'TEST-TENANT'}))
        query = db.execute.call_args.args[0].compile()
        self.assertIn('TEST-TENANT', query.params.values())
        self.assertIn('WHERE l6_signal_state.client_id', str(query))

    async def test_readonly_role_cannot_scan(self):
        with self.assertRaises(HTTPException) as caught:
            await focused_alerts.writer({'role': 'restricted_viewer'})
        self.assertEqual(caught.exception.status_code, 403)
