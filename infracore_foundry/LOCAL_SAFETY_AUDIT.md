# LOCAL SAFETY AUDIT — Satorix

## Status and scope

Recovery was paused. The original Satorix containers and the identified active image-build processes were stopped; existing application data volumes were preserved. No government/public/third-party API, cloud, messaging, model-download endpoint or external database was intentionally contacted for this audit. No package installation, image pull, browser navigation to an external site, or repository push was performed.

The static inventory covers 62 integration records and 598 repository text files at the initial scan, including all 45 BaseConnector implementations plus the inbound webhook receiver. The machine-readable inventory includes matching file/line evidence and environment-variable names/presence without secret values. Generated dependencies, binary artifacts, old database contents, SDK internals and remote CI behavior are not certified. Unknown destinations and unreviewed sources are disabled, not presumed safe.

Read [INTEGRATIONS.md](local_safe/INTEGRATIONS.md) for every identified integration, its responsible files, destinations, trigger, legacy default, credential requirements, risk classification and disabling control. [inventory.json](local_safe/inventory.json) contains detailed search evidence. Neither document is an authorization to contact the listed domains.

## Findings and minimum fixes

1. **Connector execution lacked a central approval gate.** `shared/local_safety.py` and `layer1_ingestion/connectors/base_connector.py` now reject every connector by default except CSV files resolved inside `local_safe/fixtures`. The actual REST connector remains present but disabled. HTTP CSV URLs, arbitrary files, UNC paths and other connector types are rejected. Constructor-order inspection found each existing BaseConnector subclass calls its base constructor first. No connector architecture redesign was made.
2. **Scheduled and queued work could execute persisted real source configurations.** The isolated Compose file omits Airflow entirely, streaming-worker, Ollama and ollama-init. L1 streaming entrypoint and L4/L5/L6 lifespan consumers are gated off in safe mode. Old PostgreSQL, MinIO, Redis and Kafka data are not mounted. Fresh project-scoped volumes prevent old sources, credentials, queued messages and unpaused DAG state from being replayed. Airflow being paused-at-creation alone was not considered sufficient.
3. **LLM requests and model loading were not inert.** `shared/llm/provider.py` now gates Anthropic/Ollama constructors and the provider factory. Anthropic health checks previously sent inference requests. Direct L4 query-parser initialization and L5 embeddings are suppressed. L5 entity-similarity model loading is guarded before SentenceTransformer creation. Offline/telemetry settings add defense in depth. No local Ollama/model has been approved or started.
4. **A local container could still access external networks.** `compose.local-safe.json` uses one Docker bridge with IP masquerading disabled, allowing its loopback-only published ports to remain reachable from Docker Desktop without providing routed container egress. There is no external DNS upstream, host gateway, host networking or Docker socket. Ports bind only to 127.0.0.1. `local_safe/runtime.py` adds a Python audit-hook destination/port allowlist before application imports; arbitrary hosts, metadata IPs, proxies and non-approved service ports are rejected. Only exact local service names and their resolved IPs are permitted. This hook is defense in depth, not a sandbox for malicious native code.
5. **User actions and health checks could trigger outbound operations.** The safe API launcher attaches middleware denying sync/mutation requests, inbound webhook routes, WebSockets and all `/llm` routes. GET/HEAD/OPTIONS and existing login remain available. Existing authentication is retained, using synthetic local credentials. This is intentionally limited local browsing/health operation, not full feature operation.
6. **Frontend environment overrides could transmit tokens externally.** The shared HTTP client defaults to same-origin and rejects cross-origin request URLs in safe mode. The WebSocket hook is disabled. `local_safe/frontend.mjs` starts cached Vite directly, ignores original Vite config/dotenv files, fixes the proxy to Layer 6 and sends a self-only CSP. Browser networking is separately constrained because Docker cannot contain a user's browser. No npm lifecycle scripts run.
7. **Startup itself downloaded software.** Safe Compose has no build directives, uses `pull_policy: never`, and never runs pip/npm/apt/ollama pull. Cached frontend module volumes are reused read-only; application data volumes are not. APOC auto-installation, Elasticsearch GeoIP downloads and MinIO updates are disabled. The standard Compose override makes legacy entrypoints inert, resets build/ports/dependencies, and removes networking. `scripts/start-phase-a.ps1` now stops with a quarantine error. Explicitly bypassing the override or running raw Docker/host commands is not authorized safe startup.

`LOCAL_SAFE_MODE` defaults to true in application gates and is mandatory in the safe launcher. `VITE_LOCAL_SAFE_MODE` defaults safe. Other descriptive ENABLE_* flags in Compose document the disabled policy; the enforced boundaries are the actual gates, omitted services, guarded launchers, route middleware and network configuration. Setting an ENABLE_* flag does not grant permission.

## Validation

- Original Satorix containers confirmed stopped; associated build marked Error after cancellation. No volumes deleted.
- Six standard-library policy tests passed: unknown hosts/IPs denied, only exact service/port combinations allowed, blocked routes do not reach handlers, approved CSV path accepted and other paths/connectors denied. These checks do not open external sockets or perform DNS probes.
- Safe Python files parsed; JSON configuration checks passed (16 defined services, one no-masquerade bridge, no builds, no workers/Airflow/Ollama, no environment interpolation, loopback-only ports).
- Docker Compose configuration validation passed; all required image tags and frontend dependency volumes were found locally.
- Runtime validation passed on 2026-08-30 using cached images and dependencies only. PostgreSQL, Redis, Kafka, Neo4j, Elasticsearch and MinIO reported healthy; Layers 1–6 returned HTTP 200 from their readiness endpoints; all three frontends returned HTML and transformed modules with the self-only CSP.
- Synthetic login succeeded through the intelligence frontend proxy. Auth profile, operational system-health and source-list requests returned HTTP 200. A Layer 3 mutation request was rejected with HTTP 403 by the safe middleware.
- Layers 4, 5 and 6 explicitly logged that their background Kafka consumers were disabled in local safe mode. The no-masquerade bridge allowed loopback publishing while a disposable network-disabled test to the reserved `192.0.2.0/24` documentation range confirmed no routed egress.
- Docker Desktop does not publish host ports from an `internal` or isolated bridge. The validated no-masquerade bridge is therefore intentional; changing it back makes the documented local URLs unreachable.

## Exact startup and stop commands

From PowerShell:

```powershell
Set-Location 'C:\Users\Sushant\Documents\satorix\infracore_foundry'
python -S local_safe/test_policy.py
.\scripts\start-local-safe.ps1 -CheckOnly
.\scripts\start-local-safe.ps1
```

The startup script refuses missing cached images/dependencies, never builds or pulls, starts local infrastructure, initializes only new local MinIO buckets, then checks API health in order before launching frontends. Any API failure stops the safe project. Do not resolve failures by enabling networking or installing dependencies without approval.

```powershell
docker compose --env-file local_safe/empty.env -f compose.local-safe.json -p satorix-local-safe ps
docker compose --env-file local_safe/empty.env -f compose.local-safe.json -p satorix-local-safe logs --tail 100
docker compose --env-file local_safe/empty.env -f compose.local-safe.json -p satorix-local-safe stop
```

Use http://127.0.0.1:3000, :3001 and :3002. The synthetic local login is `admin@satorix.internal` / `LocalFixtureAdminOnly123`; the API key is `local-fixture-api-key-not-production`. These are intentionally public fixture credentials, never production credentials. Use a fresh browser profile without extensions and do not reuse existing production tokens. No real `.env` is loaded by this startup.

## Safe/development controller

`scripts/start-satorix.ps1`, `stop-satorix.ps1` and `status-satorix.ps1`
provide mutually exclusive Safe and contained Development modes. Development uses
the same offline/no-masquerade boundaries and synthetic credentials but replaces
the read-only launcher so local API mutations can reach application handlers. It
uses project-scoped `satorix-development_*` data volumes and never mounts the Safe
or historical application volumes. Connector, LLM/model, Airflow, streaming,
webhook and background-consumer execution remains disabled.

The complete Safe → Development → Safe transition was runtime-validated on
2026-08-30. Development mutation traffic reached routing/application validation,
the central external-operation gate still raised `PermissionError`, the reserved
non-routable address check failed closed, and the final Safe mutation check
returned HTTP 403. Read [MODE_CONTROLLER.md](MODE_CONTROLLER.md) for commands.

The controller also exposes an explicit **Unrestricted** mode. It uses a separate
`satorix-unrestricted` Docker project and new volumes, bypasses the quarantine
override, sets `LOCAL_SAFE_MODE=false`, restores original entrypoints/networking,
and may build, download, schedule, mutate or contact external systems. It requires
a populated uncommitted `.env` and `-AcknowledgeUnrestrictedRisk`. Unrestricted
startup was intentionally not executed during the safety audit; only static and
rendered-Compose validation is permitted without explicit run-time activation.

## Remaining risks and approval boundary

- This is local containment, not an absolute guarantee against malicious dependencies, Docker/OS bugs, deliberate bypass or a separate host process. No system-wide firewall rules were applied. The main recovery process must not independently restart old containers or builds.
- Existing source configurations and credentials in old data volumes are UNKNOWN and quarantined. No attempt was made to decrypt or enumerate them. Cached images/dependencies were not rebuilt or independently supply-chain audited.
- SDK-resolved endpoints, arbitrary REST/DB/FTP/SFTP configurations, cloud provider chains, governmental gateways, file-share paths, model download internals and remote CI remain unapproved. No live API tests were used to classify them.
- Direct host Python/npm execution, explicitly selecting only the original Compose file, `docker start` on old containers, manual image builds/pulls, external CI and altered networks bypass this prescribed environment. Do not use them during safe mode.
- API source mounts are read-only; local administrator/source changes can still alter policy. Do not add external fixtures, symlinks or credentials. A malicious Python/native process is outside the audit-hook threat model. Only the supplied synthetic CSV is approved.
- Fresh empty databases may expose unrelated startup/functional defects. APOC-dependent graph functions, ingestion, scheduling, notifications, WebSockets, mutation routes, AI and training are intentionally unavailable. Existing authentication/security were not bypassed.
- Browser CSP does not control extensions, prior service workers, deliberate navigation or other applications. Old compiled frontend artifacts are not the approved frontend entrypoint.
- Any external source or broader recovery/dependency change needs explicit approval after this report. No new feature work or Layer 2-to-3 automation was implemented.
