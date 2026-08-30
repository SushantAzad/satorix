# Satorix — Company Data Intelligence & Investigation

A local-first application for importing company records, investigating relationships, reviewing explainable risk signals, and producing report snapshots with optional Gemini commentary.

**Stack:** Python · FastAPI · PostgreSQL · React · TypeScript · Cytoscape.js · Docker Compose

**Status:** working local-development MVP, under active validation. Not a production-ready compliance product. This README describes the focused application, not every historical module in the repository.

## Problem statement

Company and director records often arrive as disconnected spreadsheets. Reviewers must reconcile identifiers, find shared directors, trace relationships, distinguish missing information from low risk, and assemble evidence into a report. A director with an own recorded score of zero may still be connected to a high-risk company: conflating those measures gives a misleading picture.

Satorix connects these tasks into one workflow:

1. Validate CSV records and map them into a common entity/relationship representation.
2. Search an entity and investigate its profile, connections, and available evidence.
3. Separate own recorded risk from exposure through connected companies.
4. Generate review alerts and flag entities for personal follow-up.
5. Save a due-diligence snapshot, optionally request AI commentary, and export results.

It reduces manual navigation between records; it does **not** replace source verification, professional judgment, or a complete due-diligence investigation.

## Supported features

### CSV import and provenance

- Import **companies, directors, and directorships** through the main dashboard.
- Download templates, map columns, preview normalized rows, then confirm a saved import.
- Validate required fields, duplicate identities, dates, and company/director references.
- Merge by stable IDs. Identical entity re-imports do not create new entities; directorship writes update the existing relationship identity.
- Retain source labels, file SHA-256, and CSV row numbers, with user/tenant-scoped preview and import history.

Limits: **256 KB, 200 rows, 40 columns per file**. Original file bytes and unmapped columns are not archived. Rows commit independently; runtime failures can leave a partial import. Automatic risk calculation, fuzzy entity resolution, ownership import, and background large-file processing are not included.

### Entity search and graph investigation

- Case-insensitive substring search over names and entity IDs.
- Profiles with loaded attributes, recorded risk, source context, and available relationships.
- Interactive graph: depth selection, relationship filters, connection exploration, entity navigation, evidence inspection, zoom, pan, and fit.
- Company intelligence view showing shared-director connections and rule-based review signals.
- Source-row inspection for bundled sealed fixtures. General CSV imports provide provenance metadata, not a universal original-document viewer.

### Risk and relationship exposure

- Distinguish low, medium, high, and unknown recorded risk.
- Calculate direct-company exposure over recorded `DIRECTED` and `OWNS` links, excluding inferred links and indirect/shared-address paths.
- Keep relationship exposure separate from an entity's own score.
- Exercise varied scores and unknown values through bundled deterministic **synthetic test scenarios**, not trained or calibrated risk models.

**Example:** a director's own recorded score can remain `0` while a connected company has a score of `70`. The UI shows the connection as exposure rather than assigning the company's risk to the person.

CSV import does not automatically compute scores. Missing scores remain unknown, not zero. Relationships and review signals are not allegations of wrongdoing.

### Alerts and personal flags

- Explicit **Run signal scan** for recorded high company risk (`>=70`) and direct company exposure within the current private tenant.
- Persist the latest successful scan in PostgreSQL, with filters, pagination, acknowledgements, and notification counts.
- Preserve acknowledgements for unchanged evidence; reopen a signal when its evidence changes.
- **Flag / Unflag** on a profile adds/removes a personal watchlist entry without changing risk.

Alerts are on demand, not streaming. Resolved signals disappear from the current snapshot; this is not a permanent audit history. A dedicated watchlist investigation page with editable notes and review statuses is not implemented.

### Due-diligence snapshots and JSON exports

- Generate a fresh company, director, or project report from loaded entity, risk, relationship, exposure, and provenance data.
- Identify synthetic data, missing information, partial coverage, and recommended human checks.
- Save reports scoped to user and tenant; list, view, delete, and download JSON.
- Reports expire after **24 hours**. Download a copy for longer retention.
- Profile **Export** downloads the displayed profile as JSON, separately from the report. It does not include the full graph or saved Gemini reports.

PDF export, portfolio reports, external sanctions checks, and independent financial verification are not included.

### Optional Gemini review

- Preview an allowlisted evidence payload and explicitly consent before sending it to Google.
- Support synthetic and real imported records; keep the API key server-side.
- Bound evidence to **20 nodes, 40 relationships, and 32 KB**.
- Save the AI draft with model, timestamp, prompt version, and evidence hash in the report.
- Preserve recorded scores. Treat record text as untrusted input and render AI output as text.
- Reuse a saved review on repeat requests for the same report; no automatic retries.

Local workflows do not require Gemini. Provider availability, pricing, and quota depend on the account. A successful model listing does not guarantee generation access. AI commentary is not independently verified evidence.

## Architecture: four services, one database

The browser uses one React dashboard. Its FastAPI backend handles authentication, imports, alerts, reports, and optional Gemini requests. It calls the entity API for ontology records and relationships. Both APIs use PostgreSQL.

- **Dashboard, port 3000:** React, TypeScript, Vite, React Query, Cytoscape.js.
- **Intelligence/report API, port 8006:** FastAPI, JWT authentication, role checks for restricted operations, user workflows, and httpx integration.
- **Entity API, port 8003:** FastAPI, ontology storage, CSV write path, search, and bounded graph retrieval.
- **PostgreSQL, port 5432:** entity properties, relationships, users, watchlists, imports, alert snapshots, and report JSON.

The database image includes pgvector, but vector search is not required by this workflow. Focused Compose ports bind to loopback for local use.

### Why consolidate databases?

The earlier architecture separated graph, search, caching, and object storage across several systems. For the current bounded workflow, that added deployment and synchronization complexity without being necessary.

PostgreSQL relational tables and JSONB hold records and flexible properties. Search uses SQL substring matching; graph retrieval loads bounded tenant-visible rows and traverses relationships in memory. No separate search/graph projection is needed for focused workflows.

The trade-offs are explicit: search is not fuzzy/ranked search, and graph retrieval is limited to **5,000 entities / 10,000 relationships**. Larger workloads need indexing, query/pagination work, and benchmarks before limits can safely increase.

### Historical code versus active functionality

Connector, pipeline, graph-analytics, ML, streaming, and extra-dashboard directories remain from the earlier design. **Neo4j, Elasticsearch, Redis, MinIO, Kafka, Airflow, and the separate ML service are not required or started by focused mode.** Some legacy Python dependencies remain in the API images.

Their presence is not a claim that this dashboard offers 11+ live connectors, 17+ running microservices, production ML, or real-time streaming. Use `compose.focused.json`, not an unqualified launch of the historical `docker-compose.yml`.

## Local setup

### Prerequisites and installation boundary

- Docker with Linux containers and Docker Compose v2. The Gemini overlay needs support for `gw_priority`.
- PowerShell for the supplied scripts. The development workflow has been exercised on Windows with Docker Desktop.
- For host-side tests, Python with the required test imports, including SQLAlchemy and FastAPI for relevant modules.

**The focused launcher is not a fresh-machine installer.** It uses `--no-build --pull never` and requires these cached images:

- `pgvector/pgvector:pg15`
- `node:20-alpine`
- `infracore_foundry-layer3-api:latest`
- `infracore_foundry-layer6-api:latest`

It also requires populated external dependency volumes named `infracore_foundry_frontend_shared_modules` and `infracore_foundry_intelligence_node_modules`. Dependency manifests/lockfiles are in `layer6_dashboard/frontend/` and its `intelligence/` directory. Empty volumes alone are insufficient.

The API Dockerfiles are in `layer3_ontology/` and `layer6_dashboard/backend/`. Provisioning images and installing dependencies require network access before starting the contained runtime. An automated, verified clean-machine bootstrap remains outstanding; a fresh clone is not yet one-command ready.

### Start a prepared environment

From the repository root:

```powershell
cd infracore_foundry
.\scripts\start-focused.ps1 -CheckOnly
.\scripts\start-focused.ps1
```

Open **http://127.0.0.1:3000**. Local fixture login:

```text
Email:    admin@satorix.internal
Password: LocalFixtureAdminOnly123
```

These are deliberately public **local-demo credentials**, not production credentials. Do not expose this configuration to a public network or use it as-is for confidential deployments.

API documentation: **http://127.0.0.1:8006/docs** and **http://127.0.0.1:8003/docs**. Dashboard requests use JWT authentication; the entity API requires its configured API key.

Stop without deleting data volumes:

```powershell
.\scripts\stop-satorix.ps1 -Mode Development
```

Default focused Development permits local mutations while external integrations remain disabled. Legacy Safe and Unrestricted configurations remain separate; they are not interchangeable four-service deployment profiles. Do not run multiple modes on the same ports.

### Enable optional Gemini reports

Create `infracore_foundry/.env.gemini` locally:

```dotenv
GEMINI_API_KEY=your_private_key
GEMINI_MODEL=gemini-2.5-flash
```

This model is an example tested with one configured account, not a promise of access or free usage for all accounts.

```powershell
.\scripts\start-focused.ps1 -EnableGemini
```

Open a generated report, select **Preview data to send**, inspect it, consent, then select **Send to Gemini**. Only the report API gains an additional outbound network. A Python destination guard permits the Gemini HTTPS endpoint; this is defense in depth, not a sandbox against arbitrary native code.

After changing the key, rerun the opt-in launcher to load the configuration. Launch without the flag to return to offline focused mode. Never put a real key in a tracked example file, frontend variable, screenshot, or commit. See [Gemini and alerts](infracore_foundry/GEMINI_AND_ALERTS.md).

## Demonstration workflow

1. Open **CSV Import** at `/imports`. Import companies, then directors, then directorships. Use downloadable templates and inspect preview errors.
2. Search an imported ID/name and inspect its profile and graph. Unknown risk on a new CSV record is expected.
3. Load varied synthetic risk scenarios from `infracore_foundry`:

   ```powershell
   .\scripts\load-risk-scenarios.ps1
   ```

   This writes named synthetic records. Search **RISK LAB**, or inspect `TEST-RISK-C-001` through `TEST-RISK-C-012`.
4. Inspect `TEST-RISK-D-006`: own recorded risk is `0`, while direct company exposure appears separately.
5. Open **Alerts**, run a scan, acknowledge a signal, and rescan to verify persistence.
6. Flag/unflag an entity and download its profile JSON.
7. Generate a **Due Diligence** report, inspect limitations and source context, and download JSON. Gemini review is a separate optional action.

## Validation

From `infracore_foundry`, focused regression tests cover CSV validation, synthetic scenarios, exposure, report snapshots, search/traversal, signals, and evidence projection:

```powershell
python -m unittest tests.layer2.test_csv_import tests.layer2.test_relationship_exposure tests.layer2.test_risk_scenarios tests.layer2.test_due_diligence tests.layer2.test_focused_store tests.layer2.test_alert_signals
```

With the development containers running:

```powershell
docker exec satorix-development-intelligence-dashboard-1 npx tsc --noEmit
docker exec satorix-development-layer6-api-1 python -m unittest discover -s tests -p test_gemini_reports.py
docker exec satorix-development-layer6-api-1 python -m unittest discover -s tests -p test_focused_alerts.py
.\scripts\test-csv-import.ps1
.\scripts\test-focused.ps1
.\scripts\test-alerts-gemini.ps1
```

Smoke scripts mutate named synthetic data and may create reports or acknowledge synthetic alerts. Run the CSV smoke test before `test-focused.ps1`; load risk scenarios before the alerts test. Gemini unit tests mock Google; the alerts/Gemini smoke test checks evidence preview without generating provider content.

These checks are not exhaustive browser automation, load testing, or security certification. A short `gemini-2.5-flash` dummy-text request has succeeded with the configured account; that alone does not validate all full-report generation cases.

## Engineering decisions and limitations

- **Stable IDs, not name guesses:** deterministic merges are supported; fuzzy entity resolution is not.
- **Traceable data, not automatic truth:** hashes and source metadata help track imports, but do not establish authenticity.
- **Unknown is not safe:** absent scores and failed services must not imply zero risk or an all-clear finding.
- **Rules before AI prose:** signals are deterministic; Gemini interprets selected evidence without overwriting scores.
- **Snapshot-bound consent:** an evidence hash binds the provider request to the previewed report; report access checks user and tenant.
- **Bounded synchronous processing:** small imports/graphs simplify the application but limit scale and batch atomicity.
- **Scoped access, not a security certification:** JWT, role gates, and user/tenant filters exist; a comprehensive security review is still needed. Some ontology reads intentionally include `PLATFORM_GLOBAL` reference records.

## Remaining work

- Verified fresh-clone installation and dependency/image slimming.
- Dedicated watchlist/investigation UI with editable notes and review status.
- Full browser regression coverage, including downloads and Gemini reports/error cases.
- More actionable provider errors, quota handling, and operational monitoring.
- Larger-data query/import design and performance benchmarks.
- Production hardening: secret management, HTTPS, migrations, backups, retention policies, and security testing.

## Code guide

- [Frontend](infracore_foundry/layer6_dashboard/frontend/intelligence/src): screens, graph investigation, reports, and entity actions.
- [Dashboard API](infracore_foundry/layer6_dashboard/backend): authentication, imports, alerts, reports, Gemini, and watchlists.
- [Entity API](infracore_foundry/layer3_ontology): ontology storage, CSV writes, focused search, and graph retrieval.
- [Shared logic](infracore_foundry/shared): CSV contracts, exposure rules, signals, evidence projection, and synthetic scenarios.
- [Focused runtime](infracore_foundry/compose.focused.json) and [scripts](infracore_foundry/scripts).
- [CSV contract](infracore_foundry/CSV_IMPORT.md), [exposure semantics](infracore_foundry/RELATIONSHIP_EXPOSURE.md), [architecture notes](infracore_foundry/FOCUSED_APP.md).

## Publishing and contributing

Keep changes scoped and add regression tests for changed contracts. Before publishing, inspect staged files for secrets, real imported data, generated exports, and obsolete claims. `.env.gemini` is ignored, but ignore rules do not remove secrets already committed to Git history. Rotate any exposed key and address its history separately.

No license file is currently included. Public visibility alone does not grant an open-source license; choose and add a license before describing this as a licensed open-source release.

