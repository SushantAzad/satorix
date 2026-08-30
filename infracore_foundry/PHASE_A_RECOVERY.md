# Phase A recovery — 2026-08-28

Continues the existing recovery. No connector redesign, new features, Kafka
Layer 2-to-3 automation, authentication redesign, or dependency refactoring.
Pre-existing work and local credentials are preserved.

## Current validation

- Layers 1–6 respond to health/ping requests.
- PostgreSQL, Redis, Kafka, Neo4j, Elasticsearch and MinIO have healthy Docker checks.
- Airflow webserver and scheduler are healthy; the Celery worker responds `pong`.
- Layer 2 pipeline, run and error list endpoints return 200 against PostgreSQL.
- Layer 6's actual upstream clients reach Layers 1, 3, 4 and 5 with the existing API key.
- All three frontends render in the browser. Each serves HTML and proxies login,
  profile, sources and system-health requests successfully.
- The repeatable HTTP smoke test passes. Targeted connector export, CSV connector
  (four tests), Layer 2 lifespan and Layer 6 client regression checks pass.
- Layer 1, Layer 3 and Layer 6 fixes have been rebuilt into their images.
- **Pending:** Layer 2's full image rebuild. Its running container has the validated
  startup fix copied into it temporarily; do not recreate it from the old image.

## Fixes

### 1. REST connector public name

- Root cause: implementation defines `RestAPIConnector`, but package and registry
  import `RESTAPIConnector`.
- File: `layer1_ingestion/connectors/rest_api_connector.py`.
- Exact change: add `RESTAPIConnector = RestAPIConnector` after the class.
- Validation: package import, identity assertion and startup registry lookup pass;
  rebuilt/recreated only Layer 1; `/ping` returns 200.
- Risk: external REST authentication, pagination and provider behavior are not
  integration-tested by this startup check.

### 2. Stale webhook export

- Root cause: package imports nonexistent `WebhookConnector`; the implementation
  intentionally exposes `WebhookReceiver`, not a pull-based connector.
- File: `layer1_ingestion/connectors/__init__.py`.
- Exact change: import/export `WebhookReceiver` instead of `WebhookConnector`.
- Validation: all names in `__all__` resolve; connector export regression passes;
  existing CSV tests pass (four tests).
- Risk: callers outside the repository using the nonexistent old symbol must use
  the actual receiver name. No such callers were found in this repository.

### 3. Layer 2 missing database initialization

- Root cause: `/health` returned 200 while `/pipelines/` failed with missing
  `l2_pipeline_definitions`; the API did not initialize its registered models.
- File: `layer2_pipeline/api/app.py`.
- Exact change: add a FastAPI lifespan invoking existing `init_db()` before serving
  and `close_db()` at shutdown. Route imports already register Layer 2 models.
- Validation: restart with the patch; logs confirm database creation/connectivity;
  `/health`, `/pipelines/`, `/runs/`, `/errors/` return 200. Lifecycle regression passes.
- Risk: `create_all` creates missing tables but is not a migration engine for
  incompatible schemas. Full pipeline execution and the Kafka automation gap remain
  outside this recovery validation.

### 4. Layer 3 import failure

- Root cause: actions route still uses `Query` after an earlier import edit removed it.
- File: `layer3_ontology/api/routes/actions.py`.
- Exact change: restore `Query` in the existing FastAPI import; preserve other edits.
- Validation: rebuilt Layer 3 starts, seeds schema registry, and `/health` reports
  PostgreSQL, Neo4j, Elasticsearch and Redis as `ok`.
- Risk: business action execution is not covered by startup validation.

### 5. Concurrent first-start initialization

- Root cause: multiple Uvicorn workers ran schema initialization concurrently.
  Layers 3–6 produced PostgreSQL type/table unique violations; Layer 3 also had
  Neo4j deadlocks and Elasticsearch index-creation conflicts; Layer 6 raced admin creation.
- File: `docker-compose.yml`.
- Exact change: explicit existing Uvicorn commands with `--workers 1` for Layers 3–6.
- Validation: affected APIs recreated individually; startup succeeds, dependency
  checks pass, Layer 6 login works and Kafka consumers connect.
- Risk: single-worker throughput. This local fix does not serialize initialization
  across multiple container replicas or direct runs using Dockerfile defaults.

### 6. Layer 6 did not send the upstream API key

- Root cause: Layer 6 had neither the shared key in Compose nor default client
  headers; real Layer 1 calls returned 401 and were masked as empty results.
- Files: `docker-compose.yml`, `layer6_dashboard/backend/core/config.py`,
  `layer6_dashboard/backend/core/layer_clients.py`.
- Exact change: pass existing `API_KEY` to Layer 6, expose it in settings, and set
  `X-API-Key` on its four existing HTTP clients. No key is exposed to the frontend.
- Validation: live upstream requests and client regression pass, including
  protected Layer 3 action-type listing; proxied sources return 200.
- Risk: existing broad exception-to-empty-result behavior remains. This is not an
  authorization or tenant-isolation audit.

### 7. Layer 6 source collection redirects

- Root cause: source list/create used `/api/v1/sources`, which Layer 1 redirects
  with HTTP 307; the client does not follow redirects and treats that as failure.
- File: `layer6_dashboard/backend/core/layer_clients.py`.
- Exact change: use `/api/v1/sources/` for collection GET and POST.
- Validation: observed original 307; corrected real GET returns 200; mock transport
  regression verifies GET and POST use the canonical path.
- Risk: other application routes were not exhaustively audited.

## Reproducible startup

Prerequisites: Docker Desktop Linux engine running; existing `.env` populated
using `.env.example`; ports 5432, 6379, 8001–8006, 3000–3002 and infrastructure
ports available; network and disk space for image and npm downloads.

From PowerShell:

```powershell
Set-Location C:\Users\Sushant\Documents\satorix\infracore_foundry
.\scripts\start-phase-a.ps1
```

The script validates Compose, builds all seven application/worker images,
starts infrastructure and waits for Docker health checks, runs MinIO/Airflow
initializers, starts Airflow, starts each API with an HTTP readiness gate, starts
the streaming worker, and starts the three frontends sequentially. It ends with
`scripts/smoke-phase-a.py`, executed inside Layer 6 with existing environment
credentials. Failed commands/readiness checks stop the script.

Use `-SkipBuild` only when images already contain the current fixes.
The script never runs `down`, removes volumes, or resets application data.
First-time Layer 2 builds download large ML/CUDA dependencies from the existing
shared requirements; downloads can take substantial time.

Repeat HTTP validation independently:

```powershell
Get-Content -Raw scripts/smoke-phase-a.py | docker compose exec -T layer6-api python -
docker compose ps -a
```

Applications: intelligence `http://localhost:3000`, operations
`http://localhost:3001`, schema `http://localhost:3002`. Login uses the configured
`DEFAULT_ADMIN_EMAIL` and `DEFAULT_ADMIN_PASSWORD` from `.env`; credentials are
not reproduced here.

## Remaining limitations

- LLM provider credentials are absent; Layer 5 reports fallback mode. Optional
  Ollama and model-download services are not started for the current Anthropic
  configuration. No model download or paid inference was initiated.
- Streaming worker is intentionally idle without `KAFKA_TOPICS` configuration.
- No new ingestion data, end-to-end business pipeline, LLM inference, or Kafka
  Layer 2-to-3 automation was added or claimed as tested.
- npm reports dependency vulnerabilities; no broad upgrade or audit fix was run.
- Schema UI has an existing React list-key warning and placeholder property counts.
- Operational health marks non-HTTP PostgreSQL/Redis/Kafka/Bolt checks `unknown`
  and returns no DAG data; Docker health verifies those dependencies separately.
- Some dashboards use fallback/empty responses for unavailable business endpoints.
  Passing startup checks does not certify every feature.
- Local runtime uses existing development credentials/settings and is not a
  production security sign-off.

## Added validation files

- `tests/layer1/test_connector_exports.py`
- `tests/layer2/test_startup.py`
- `layer6_dashboard/backend/tests/test_layer_clients.py`
- `scripts/smoke-phase-a.py`
- `scripts/start-phase-a.ps1` (PowerShell syntax checked; full script execution pending)
