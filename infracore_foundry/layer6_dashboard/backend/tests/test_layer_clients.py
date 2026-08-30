"""Upstream wiring regression tests; no live services required."""
import unittest
from unittest.mock import patch

import httpx

from core.layer_clients import LayerClients, settings


class LayerClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_key_and_source_collection_routes(self):
        with patch.object(settings, "api_key", "test-upstream-key"):
            clients = LayerClients()
        try:
            for client in (clients.l1_client, clients.l3_client,
                           clients.l4_client, clients.l5_client):
                self.assertEqual(client.headers["X-API-Key"], "test-upstream-key")

            requests = []

            def respond(request):
                requests.append(request)
                if request.method == "POST":
                    return httpx.Response(201, json={"id": "test-source"})
                return httpx.Response(200, json=[{"id": "test-source"}])

            await clients.l1_client.aclose()
            clients.l1_client = httpx.AsyncClient(
                base_url="http://layer1-api:8001",
                transport=httpx.MockTransport(respond),
            )
            self.assertEqual(await clients.get_sources(), [{"id": "test-source"}])
            self.assertEqual(await clients.create_source({}), {"id": "test-source"})
            self.assertEqual([r.url.path for r in requests],
                             ["/api/v1/sources/", "/api/v1/sources/"])
        finally:
            await clients.close()


if __name__ == "__main__":
    unittest.main()
