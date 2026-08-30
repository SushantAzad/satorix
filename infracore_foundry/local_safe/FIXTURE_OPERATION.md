# Phase 2: initial company-fixture operation

## Exact exception

The Local Safe launcher opts **only Layer 1** into one authenticated mutation:
`POST /api/v1/fixtures/import` with exactly
`{"fixture_id":"company_investigation_v1"}`. No query parameters, paths, URLs,
connector options, source configurations, destinations, or additional fields are
accepted. Requests larger than 1 KiB are denied. Other services retain the original
read-only middleware policy. General sync, webhooks, REST connectors, external
providers, workers, and model downloads are not enabled.

This phase authorizes the **four initial CSVs only**. The update CSV remains a
specification for a later phase; it cannot be selected through this endpoint.

Authorization requires explicit `LOCAL_SAFE_MODE=true`, the fixed registry entry,
the existing local-fixture API key, the safe launcher's installed egress guard,
and exact safe PostgreSQL/MinIO configuration. The route also checks independently,
so omitting the middleware does not authorize the operation. No real credentials
are used. PostgreSQL must be `postgres:5432/satorix_safe` with the existing fixture
account; MinIO must be `http://minio:9000`, bucket `raw-data`, fixture credentials.
The bound DB URL and cached MinIO endpoint are checked before persistence.

## Containment and contract

Only registry-supplied filenames are resolved under
`local_safe/fixtures/company_investigation_v1`. Resolved root, directory, and file
paths must not be redirected by symlinks/junctions or leave the approved directory.
The four CSVs, expected-results JSON, and contract document are SHA-256 pinned.
Changing bytes, including line endings, requires deliberate registry review.
The approved contract version, source ID, and local demo client context are checked.
Input and batch identity follow Phase 1's exact-byte checksum recipe.

Read-only mounts and isolated Docker networking are still required. These checks
are not protection against a malicious process that can modify trusted Python or
replace files during execution. No system-wide firewall changes are made.

## Synthetic identity decision

An authorized fixture context supplies `demo_identity(entity_type, value)` for
exactly the known DEMO identities in this fixture. It returns a descriptor with
`scheme=local-demo-v1`, `synthetic=true`, explicit entity type and local client ID.
It does not construct a Company/Director ontology object, populate `cin` or `din`,
or convert a DEMO ID to a government-style identifier. Global validators are
untouched and continue rejecting DEMO IDs. No generic adapter API is exposed.

Unknown/malformed/blank raw IDs remain unchanged in raw records; their descriptor
is null. All 24 rows are ingested, including the five malformed and one ambiguous
record. Filtering, review decisions, matching, and ontology adaptation remain
later phases. This is not an implementation of entity resolution.

## Existing Layer 1 machinery reused

The operation uses CSVConnector.extract_full, ExtractionConfig, SourceRegistry
lookup, DataSource/SyncState/SyncRun models, existing credential encryption, and
the existing upload_parquet/object_exists storage helpers. It does not call
general SyncEngine because that includes broader orchestration/processing and
hourly batch semantics inconsistent with this fixed fixture contract.

One deterministic source UUID represents the four-file bundle; its encrypted
configuration contains only the fixture ID. A transaction-scoped advisory lock
spans registration, extraction, raw writes, and completion. The adapter inserts
the existing models directly rather than calling create_source, whose internal
commits would release that lock. No database schema is changed.

Every raw row preserves original columns, source_record_id, filename, CSV line
number (header is line 1), source/client IDs, batch ID, run ID, and demo descriptors.
Raw output uses deterministic keys below
`raw-data/local-company-investigation/<source_id>/<batch_id>/`.
Replay reuses a completed SyncRun after checking all four objects exist. A failed
upload is surfaced and the run marked failed where DB writes remain possible.
Partial MinIO objects can remain and are overwritten on retry; no distributed
transaction or tested concurrency guarantee is claimed. No L2/L3 work is triggered.

## Offline verification and blockers

Commands from repository root:

    python -B local_safe/test_policy.py
    python -B local_safe/fixtures/company_investigation_v1/test_consistency.py
    python -B local_safe/test_fixture_operation.py

The new tests use actual CSV extraction and existing model/registry classes with
mocked PostgreSQL and MinIO. Missing MinIO and eager connector imports are isolated
in the test harness, not changed in production. No network or service is used by
the new suite. Global identity validators are exercised without modifying them.

**Known pre-existing configuration blocker:** the encryption key currently in
compose.local-safe.json decodes to 33 bytes; existing encryption requires 32. The
operation now refuses it before opening a DB session. Tests use an explicitly
synthetic valid 32-byte test key. Docker configuration was not changed. Correcting
the disposable environment's key requires separate approval before live validation.

The host Python lacks FastAPI and MinIO; no packages were installed. HTTP framework
integration and actual database/object-store execution therefore remain unverified.
The MinIO endpoint check deliberately fails closed if a cached SDK version exposes
an incompatible endpoint representation. No Docker startup occurred. Do not mark
the runnable workflow complete based on these offline tests or proceed to Phase 3.

Recorded offline results for this change: 6 existing policy tests passed, 6 Phase 1
consistency tests passed, 15 new operation tests passed, 7 changed/new Python modules
parsed successfully, and Ruff checks passed. The existing connector-export unit
test was attempted and failed at import because `minio` is not installed on the
host. This is a reported validation blocker, not a passing or skipped test.
