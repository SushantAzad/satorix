"""Run via stdin in layer6-api; checks existing services without printing secrets.

Reads only, except login updates the existing administrator's last_login.
No test data or ingestion jobs are created.
"""
import asyncio
import os

import httpx


def expect(response):
    response.raise_for_status()
    return response.json()


async def check_upstream_clients():
    from core.layer_clients import layer_clients

    try:
        for name, client, path in [
            ("L1 sources", layer_clients.l1_client, "/api/v1/sources/"),
            ("L3 action types", layer_clients.l3_client, "/actions/types"),
            ("L4 health", layer_clients.l4_client, "/api/v1/health"),
            ("L5 health", layer_clients.l5_client, "/api/v1/health"),
        ]:
            expect(await client.get(path))
            print(f"PASS BFF upstream {name}")
    finally:
        await layer_clients.close()


def main():
    paths = {1: "/ping", 2: "/health", 3: "/health",
             4: "/api/v1/health", 5: "/api/v1/health", 6: "/health"}
    with httpx.Client(timeout=20) as client:
        for layer, path in paths.items():
            data = expect(client.get(f"http://layer{layer}-api:800{layer}{path}"))
            if layer == 1:
                assert data.get("pong") is True, data
            else:
                assert data.get("status") in ("ok", "healthy"), data
            print(f"PASS Layer {layer} health")
        for path in ("/pipelines/", "/runs/", "/errors/"):
            expect(client.get("http://layer2-api:8002" + path,
                              headers={"X-API-Key": os.environ["API_KEY"]}))
            print(f"PASS Layer 2 {path}")

    asyncio.run(check_upstream_clients())

    credentials = {"email": os.environ["DEFAULT_ADMIN_EMAIL"],
                   "password": os.environ["DEFAULT_ADMIN_PASSWORD"]}
    for port in (3000, 3001, 3002):
        # Match the browser's localhost Host header; keep Vite host checks intact.
        with httpx.Client(base_url=f"http://host.docker.internal:{port}", timeout=20,
                          headers={"Host": f"localhost:{port}"}) as client:
            response = client.get("/")
            response.raise_for_status()
            assert "text/html" in response.headers.get("content-type", "")
            login = expect(client.post("/api/v1/auth/login", json=credentials))
            auth = {"Authorization": "Bearer " + login["access_token"]}
            expect(client.get("/api/v1/auth/me", headers=auth))
            expect(client.get("/api/v1/sources/", headers=auth))
            status = expect(client.get("/api/v1/operational/system-health", headers=auth))
            layers = [s for s in status["services"] if s["name"].startswith("layer")]
            assert len(layers) == 5 and all(s["status"] == "healthy" for s in layers)
            print(f"PASS frontend {port}: HTML, login, profile, sources, upstream health")
    print("Phase A HTTP smoke checks passed.")


if __name__ == "__main__":
    main()
