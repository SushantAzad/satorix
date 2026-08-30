import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import HTTPException
from api.routes import gemini
from shared.gemini_evidence import project_evidence


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    def setup_report(self):
        content = {'entity_type': 'company', 'entity_id': 'TEST', 'sections': {}}
        return SimpleNamespace(report_content=content), gemini.Consent(consent=True, evidence_sha256=project_evidence(content)[1])

    async def test_consent_required(self):
        with self.assertRaises(HTTPException) as caught:
            await gemini.enrich(uuid4(), gemini.Consent(consent=False, evidence_sha256=''), {}, AsyncMock())
        self.assertEqual(caught.exception.status_code, 422)

    async def test_disabled_no_network(self):
        row, body = self.setup_report()
        with patch.object(gemini, 'owned', AsyncMock(return_value=row)), patch.object(gemini, 'configuration', return_value={'ready': False, 'message': 'disabled'}):
            with self.assertRaises(HTTPException) as caught:
                await gemini.enrich(uuid4(), body, {}, AsyncMock())
            self.assertEqual(caught.exception.status_code, 503)

    async def test_completed_output_cached_and_scores_unchanged(self):
        row, body = self.setup_report()
        db = AsyncMock()
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Recorded facts: TEST. Human review required.'}]}}]})
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with patch.object(gemini, 'owned', AsyncMock(return_value=row)), patch.object(gemini, 'configuration', return_value={'ready': True, 'model': 'gemini-test'}), patch.object(gemini.httpx, 'AsyncClient', return_value=client), patch.dict(gemini.os.environ, {'GEMINI_API_KEY': 'mock-not-real'}):
            first = await gemini.enrich(uuid4(), body, {}, db)
            second = await gemini.enrich(uuid4(), body, {}, db)
            self.assertEqual(first, second)
            self.assertEqual(client.post.await_count, 1)
            self.assertEqual(list(row.report_content['sections']), ['gemini_ai_review'])
            self.assertNotIn('mock-not-real', str(first))

    async def test_blocked_output_not_saved(self):
        row, body = self.setup_report()
        db = AsyncMock()
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'candidates': []})
        with patch.object(gemini, 'owned', AsyncMock(return_value=row)), patch.object(gemini, 'configuration', return_value={'ready': True, 'model': 'gemini-test'}), patch.object(gemini.httpx, 'AsyncClient', return_value=client), patch.dict(gemini.os.environ, {'GEMINI_API_KEY': 'mock-not-real'}):
            with self.assertRaises(HTTPException):
                await gemini.enrich(uuid4(), body, {}, db)
            db.commit.assert_not_awaited()
            self.assertEqual(row.report_content['sections'], {})

    def test_safe_configuration_is_disabled(self):
        with patch.dict(gemini.os.environ, {'LOCAL_SAFE_MODE': 'true', 'DEVELOPMENT_MODE': 'false', 'GEMINI_ENABLED': 'true', 'SATORIX_GEMINI_EGRESS': 'true', 'GEMINI_API_KEY': 'mock', 'GEMINI_MODEL': 'gemini-test'}):
            self.assertFalse(gemini.configuration()['ready'])

    async def test_report_lookup_is_owner_tenant_and_expiry_scoped(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
        user_id, report_id = uuid4(), uuid4()
        with self.assertRaises(HTTPException) as caught:
            await gemini.owned(db, {'sub': str(user_id), 'client_id': 'TENANT-TEST'}, report_id, True)
        self.assertEqual(caught.exception.status_code, 404)
        query = db.execute.call_args.args[0].compile()
        self.assertIn('TENANT-TEST', query.params.values())
        self.assertIn(user_id, query.params.values())
        self.assertIn(report_id, query.params.values())
        self.assertIn('expires_at >', str(query))
        self.assertIn('FOR UPDATE', str(query))
