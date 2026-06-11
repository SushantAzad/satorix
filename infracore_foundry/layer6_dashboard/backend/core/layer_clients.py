"""
Layer 6 upstream HTTP clients — thin async wrappers around Layer 1, 3, 4, and 5 APIs.

ALL methods catch exceptions and return None / empty list on failure so that
a single unavailable layer never crashes a dashboard request.

Multi-tenancy:
  Every Layer 3 / Layer 4 call that returns graph or ontology data accepts an
  optional `client_id` parameter and forwards it as the `X-Client-ID` header.
  Layer 3 reads the header and applies per-tenant Cypher / SQL / ES filters so
  that Client A can never see Client B's private data.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

PLATFORM_GLOBAL = "PLATFORM_GLOBAL"

# Default timeout for all upstream calls (seconds)
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _client_headers(client_id: str) -> Dict[str, str]:
    """Build the X-Client-ID header dict for a given tenant."""
    return {"X-Client-ID": client_id}


class LayerClients:
    """Aggregated HTTP client for all upstream Satorix layers."""

    def __init__(self) -> None:
        self.l1_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.layer1_api_url,
            timeout=_TIMEOUT,
        )
        self.l3_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.layer3_api_url,
            timeout=_TIMEOUT,
        )
        self.l4_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.layer4_api_url,
            timeout=_TIMEOUT,
        )
        self.l5_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.layer5_api_url,
            timeout=_TIMEOUT,
        )

    async def close(self) -> None:
        """Close all underlying HTTP clients."""
        for client in (self.l1_client, self.l3_client, self.l4_client, self.l5_client):
            try:
                await client.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error closing HTTP client: %s", exc)

    # ------------------------------------------------------------------
    # Layer 3 — Ontology
    # ------------------------------------------------------------------

    async def get_entity(
        self,
        entity_type: str,
        entity_id: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[Dict]:
        """GET /objects/{entity_type}/{entity_id} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                f"/objects/{entity_type}/{entity_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_entity(%s, %s) failed: %s", entity_type, entity_id, exc)
            return None

    async def search_entities(
        self,
        query: str,
        limit: int = 10,
        client_id: str = PLATFORM_GLOBAL,
    ) -> List[Dict]:
        """GET /search?q={query}&size={limit} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                "/search",
                params={"q": query, "size": limit},
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            data = resp.json() or {}
            if isinstance(data, dict):
                return data.get("results", [])
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("search_entities('%s') failed: %s", query, exc)
            return []

    async def get_network(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 2,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[Dict]:
        """GET /graph/network/{entity_type}/{entity_id}?depth={depth} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                f"/graph/network/{entity_type}/{entity_id}",
                params={"depth": depth},
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "get_network(%s, %s, depth=%s) failed: %s",
                entity_type, entity_id, depth, exc,
            )
            return None

    async def get_risk_score(
        self,
        entity_type: str,
        entity_id: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[Dict]:
        """GET /intelligence/risk/{entity_type}/{entity_id} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                f"/intelligence/risk/{entity_type}/{entity_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "get_risk_score(%s, %s) failed: %s", entity_type, entity_id, exc
            )
            return None

    async def get_alerts(
        self,
        entity_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        client_id: str = PLATFORM_GLOBAL,
    ) -> List[Dict]:
        """GET /intelligence/alerts with optional query params from Layer 3."""
        params: Dict[str, Any] = {"limit": limit}
        if entity_id:
            params["entity_id"] = entity_id
        if severity:
            params["severity"] = severity
        try:
            resp = await self.l3_client.get(
                "/intelligence/alerts",
                params=params,
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            data = resp.json() or []
            if isinstance(data, dict):
                return data.get("alerts", [])
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("get_alerts() failed: %s", exc)
            return []

    async def get_alert(
        self, alert_id: str, client_id: str = PLATFORM_GLOBAL
    ) -> Optional[Dict]:
        """GET /intelligence/alerts/{alert_id} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                f"/intelligence/alerts/{alert_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_alert(%s) failed: %s", alert_id, exc)
            return None

    async def get_timeline(
        self,
        entity_type: str,
        entity_id: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> List[Dict]:
        """GET /timeline/{entity_type}/{entity_id} from Layer 3."""
        try:
            resp = await self.l3_client.get(
                f"/timeline/{entity_type}/{entity_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json() or []
        except Exception as exc:
            logger.warning(
                "get_timeline(%s, %s) failed: %s", entity_type, entity_id, exc
            )
            return []

    async def trigger_ingest(self, source_id: str) -> Optional[Dict]:
        """POST /ingest/trigger to Layer 1 (via l1_client)."""
        try:
            resp = await self.l1_client.post(
                "/ingest/trigger", json={"source_id": source_id}
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("trigger_ingest(%s) failed: %s", source_id, exc)
            return None

    # ------------------------------------------------------------------
    # Layer 4 — Graph Intelligence
    # ------------------------------------------------------------------

    async def get_l4_network(
        self,
        entity_type: str,
        entity_id: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[Dict]:
        """GET /graph/network/{entity_type}/{entity_id} from Layer 4."""
        try:
            resp = await self.l4_client.get(
                f"/graph/network/{entity_type}/{entity_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "get_l4_network(%s, %s) failed: %s", entity_type, entity_id, exc
            )
            return None

    async def get_influence_scores(
        self,
        entity_type: str,
        entity_id: str,
        client_id: str = PLATFORM_GLOBAL,
    ) -> Optional[Dict]:
        """GET /intelligence/influence/{entity_type}/{entity_id} from Layer 4."""
        try:
            resp = await self.l4_client.get(
                f"/intelligence/influence/{entity_type}/{entity_id}",
                headers=_client_headers(client_id),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "get_influence_scores(%s, %s) failed: %s", entity_type, entity_id, exc
            )
            return None

    # ------------------------------------------------------------------
    # Layer 5 — ML / Analytics
    # ------------------------------------------------------------------

    async def get_cirp_prediction(self, cin: str) -> Optional[Dict]:
        """GET /api/v1/predictions/cirp/{cin} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/predictions/cirp/{cin}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_cirp_prediction(%s) failed: %s", cin, exc)
            return None

    async def get_project_prediction(self, project_id: str) -> Optional[Dict]:
        """GET /api/v1/predictions/project/{project_id} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/predictions/project/{project_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_project_prediction(%s) failed: %s", project_id, exc)
            return None

    async def get_trends(self, entity_id: str, entity_type: str = "company") -> Optional[Dict]:
        """GET /api/v1/analytics/trends/{entity_type}/{entity_id} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/analytics/trends/{entity_type}/{entity_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_trends(%s) failed: %s", entity_id, exc)
            return None

    async def get_benchmark(self, entity_id: str, entity_type: str = "company") -> Optional[Dict]:
        """GET /api/v1/analytics/benchmarks/{entity_type}/{entity_id} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/analytics/benchmarks/{entity_type}/{entity_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_benchmark(%s) failed: %s", entity_id, exc)
            return None

    async def generate_narrative(
        self,
        entity_type: str,
        entity_id: str,
        context: Dict,
    ) -> Optional[str]:
        """POST /api/v1/llm/entity-intelligence to Layer 5; returns the narrative string."""
        try:
            resp = await self.l5_client.post(
                "/api/v1/llm/entity-intelligence",
                json={"entity_type": entity_type, "entity_id": entity_id, "context": context},
                timeout=150.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("narrative") or data.get("text") or data.get("summary") or str(data)
        except Exception as exc:
            logger.warning(
                "generate_narrative(%s, %s) failed: %s", entity_type, entity_id, exc
            )
            return None

    async def generate_report(
        self,
        entity_type: str,
        entity_id: str,
        report_type: str,
    ) -> Optional[Dict]:
        """POST /api/v1/reports/generate to Layer 5."""
        try:
            resp = await self.l5_client.post(
                "/api/v1/reports/generate",
                json={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "report_type": report_type,
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "generate_report(%s, %s, %s) failed: %s",
                entity_type,
                entity_id,
                report_type,
                exc,
            )
            return None

    async def get_report_status(self, report_id: str) -> Optional[Dict]:
        """GET /api/v1/reports/{report_id} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/reports/{report_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_report_status(%s) failed: %s", report_id, exc)
            return None

    async def get_model_performance(self) -> Optional[Dict]:
        """GET /api/v1/observability/metrics from Layer 5."""
        try:
            resp = await self.l5_client.get("/api/v1/observability/metrics")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_model_performance() failed: %s", exc)
            return None

    async def ask_intelligence_question(
        self, question: str, cin: Optional[str] = None
    ) -> Optional[Dict]:
        """POST /api/v1/agents/intelligence/query — open-ended reasoning query."""
        try:
            resp = await self.l5_client.post(
                "/api/v1/agents/intelligence/query",
                json={"question": question, "cin": cin},
                timeout=300.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("ask_intelligence_question failed: %s", exc)
            return None

    async def get_entity_features(self, cin: str) -> Optional[Dict]:
        """GET /api/v1/predictions/features/{cin} — computed intelligence features."""
        try:
            resp = await self.l5_client.get(f"/api/v1/predictions/features/{cin}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_entity_features(%s) failed: %s", cin, exc)
            return None

    async def get_correlations(self, cin: str) -> Optional[Dict]:
        """GET /api/v1/analytics/correlations/{cin} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/analytics/correlations/{cin}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_correlations(%s) failed: %s", cin, exc)
            return None

    async def get_scenarios(self, cin: str) -> Optional[Dict]:
        """GET /api/v1/scenarios/{cin} from Layer 5."""
        try:
            resp = await self.l5_client.get(f"/api/v1/scenarios/{cin}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_scenarios(%s) failed: %s", cin, exc)
            return None

    # ------------------------------------------------------------------
    # Layer 1 — Source / Ingestion
    # ------------------------------------------------------------------

    async def get_sources(self, client_id: Optional[str] = None) -> List[Dict]:
        """GET /api/v1/sources from Layer 1."""
        params: Dict[str, Any] = {}
        if client_id:
            params["client_id"] = client_id
        try:
            resp = await self.l1_client.get("/api/v1/sources", params=params)
            resp.raise_for_status()
            return resp.json() or []
        except Exception as exc:
            logger.warning("get_sources() failed: %s", exc)
            return []

    async def test_source(self, source_id: str) -> Optional[Dict]:
        """POST /api/v1/sources/{source_id}/test to Layer 1."""
        try:
            resp = await self.l1_client.post(f"/api/v1/sources/{source_id}/test")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("test_source(%s) failed: %s", source_id, exc)
            return None

    async def get_source_health(self) -> List[Dict]:
        """GET /api/v1/health/sources from Layer 1."""
        try:
            resp = await self.l1_client.get("/api/v1/health/sources")
            resp.raise_for_status()
            return resp.json() or []
        except Exception as exc:
            logger.warning("get_source_health() failed: %s", exc)
            return []

    async def create_source(self, source_data: Dict) -> Optional[Dict]:
        """POST /api/v1/sources to Layer 1."""
        try:
            resp = await self.l1_client.post("/api/v1/sources", json=source_data)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("create_source() failed: %s", exc)
            return None

    async def get_source_by_id(self, source_id: str) -> Optional[Dict]:
        """GET /api/v1/sources/{source_id} from Layer 1."""
        try:
            resp = await self.l1_client.get(f"/api/v1/sources/{source_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_source_by_id(%s) failed: %s", source_id, exc)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton (initialised in api/main.py lifespan)
# ---------------------------------------------------------------------------
layer_clients = LayerClients()
