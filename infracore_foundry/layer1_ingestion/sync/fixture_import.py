"""Bounded Layer 1 adapter: existing CSV extraction, source/run tables and storage.

No processing, entity resolution, ontology writes, worker or general connector dispatch.
"""
from datetime import datetime, timezone
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from shared.fixture_operation import (
    CLIENT_ID, CONTRACT_VERSION, FILES, FIXTURE_ID, SOURCE_ID,
    authorize_fixture, expected_rows, require_local_storage, require_runtime_guard,
)


def _extract_frames(approved, source_uuid, run_id):
    from layer1_ingestion.connectors.csv_connector import CSVConnector
    from layer1_ingestion.connectors.base_connector import ExtractionConfig
    frames = []
    for path in approved.paths:
        # Connector selection/config is fixed here, never taken from request or DB.
        connector = CSVConnector(str(source_uuid), {
            "file_path": str(path), "encoding": "utf-8", "delimiter": ",",
            "has_header": True,
        })
        frame = connector.extract_full(ExtractionConfig(source_id=str(source_uuid), client_id=CLIENT_ID))
        frame = frame.fillna("")
        records = expected_rows(path)
        if frame.to_dict(orient="records") != records:
            raise ValueError("CSV extraction did not preserve the approved source records")
        if frame["source_record_id"].duplicated().any():
            raise ValueError("Duplicate source record identifiers")
        identities = []
        for record in records:
            descriptors = {}
            for field, kind in (("company_id", "Company"), ("director_id", "Director"), ("address_id", "Address")):
                if field in record:
                    try:
                        descriptors[field] = approved.demo_identity(kind, record[field])
                    except PermissionError:
                        # Malformed/unresolved rows remain RAW input, not rejected
                        # or silently coerced into government/ontology identities.
                        descriptors[field] = None
            identities.append(json.dumps(descriptors, sort_keys=True))
        frame["_demo_identities"] = identities
        frame["_identity_scheme"] = "local-demo-v1"
        frame["_source_filename"] = path.name
        frame["_source_row_number"] = range(2, len(frame) + 2)
        frame["_source_id"] = SOURCE_ID
        frame["_registry_source_id"] = str(source_uuid)
        frame["_client_id"] = CLIENT_ID
        frame["_batch_id"] = approved.batch_id
        frame["_run_id"] = str(run_id)
        frame["_contract_version"] = CONTRACT_VERSION
        frames.append((path.name, frame))
    # Detect changed fixtures between authorization and extraction. Read-only
    # Docker mounts remain necessary; this is not a hostile-host file sandbox.
    if authorize_fixture({"fixture_id": FIXTURE_ID}) != approved:
        raise PermissionError("Fixture changed during extraction")
    return frames


def _verify_bound_clients(db, storage):
    url = db.get_bind().url
    if (url.get_backend_name() != "postgresql" or url.host != "postgres" or
            url.port != 5432 or url.database != "satorix_safe" or
            url.username != "satorix_safe" or url.password != "LocalFixturePasswordOnly123" or url.query):
        raise PermissionError("Database session is not bound to safe storage")
    client = storage.get_minio_client()
    # Fail closed if the cached SDK client differs from validated settings (or
    # its installed version does not expose this endpoint representation).
    endpoint = getattr(getattr(client, "_base_url", None), "_url", None)
    if (getattr(endpoint, "hostname", None), getattr(endpoint, "port", None),
            getattr(endpoint, "scheme", None)) != ("minio", 9000, "http"):
        raise PermissionError("MinIO client is not bound to safe storage")


def _persist(approved, db, storage):
    from sqlalchemy import text
    from layer1_ingestion.core.encryption import encrypt_credential
    from layer1_ingestion.registry.models import DataSource, SyncRun, SyncState
    from layer1_ingestion.registry.source_registry import SourceRegistry

    _verify_bound_clients(db, storage)
    # Transaction lock spans registration, extraction, writes and commit. Unlike
    # general sync, there is no intermediate commit that releases the lock.
    lock_key = int(approved.batch_id[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    source_uuid = uuid5(NAMESPACE_URL, CLIENT_ID + ":" + SOURCE_ID)
    source = SourceRegistry(db).get_source(source_uuid)
    if source is None:
        source = DataSource(
            id=source_uuid, client_id=CLIENT_ID, source_name=SOURCE_ID,
            source_type="csv", environment="local-safe", status="active",
            connection_config=encrypt_credential(json.dumps({"fixture_id": FIXTURE_ID})),
            description="Synthetic fixture bundle; fixture route only", created_by="local-fixture-operation",
        )
        db.add(source)
        db.flush()
        db.add(SyncState(source_id=source_uuid, status="idle"))
    elif (source.client_id, source.source_name, source.source_type, source.environment) != (
            CLIENT_ID, SOURCE_ID, "csv", "local-safe"):
        raise PermissionError("Existing source is not the approved local fixture source")
    run = db.query(SyncRun).filter(SyncRun.batch_id == approved.batch_id).first()
    prefix = f"local-company-investigation/{SOURCE_ID}/{approved.batch_id}"
    outputs = {name: f"{prefix}/{name[:-4]}.parquet" for name in FILES}
    if run is not None and run.source_id != source_uuid:
        raise PermissionError("Batch is owned by a different source")
    if run is not None and run.status == "completed":
        # Missing objects are not silently reported as a successful replay.
        if not all(storage.object_exists("raw-data", key) for key in outputs.values()):
            raise RuntimeError("Completed fixture batch has missing raw objects")
        db.commit()
        return _result(approved, run, outputs, "already_applied")
    if run is None:
        run = SyncRun(id=uuid4(), source_id=source_uuid, batch_id=approved.batch_id, sync_type="fixture", status="running")
        db.add(run)
    run.status, run.error_details = "running", None
    db.flush()
    try:
        frames = _extract_frames(approved, source_uuid, run.id)
        for name, frame in frames:
            storage.upload_parquet(frame, "raw-data", outputs[name], extra_metadata={
                "fixture_id": FIXTURE_ID, "input_checksum": approved.input_checksum,
                "batch_id": approved.batch_id, "client_id": CLIENT_ID,
            })
        run.records_extracted = sum(len(frame) for _, frame in frames)
        run.records_failed = 0  # Raw extraction includes malformed business records.
        run.output_path = prefix
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return _result(approved, run, outputs, "completed")
    except Exception:
        # Partial raw objects may remain; deterministic keys are overwritten on
        # retry, but this is not an atomic PostgreSQL/MinIO transaction.
        run.status = "failed"
        run.error_details = "Fixture extraction/storage failed; inspect local logs"
        run.completed_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise


def _result(approved, run, outputs, status):
    return {"status": status, "fixture_id": FIXTURE_ID, "source_id": SOURCE_ID,
            "client_id": CLIENT_ID, "batch_id": approved.batch_id,
            "input_checksum": approved.input_checksum, "run_id": str(run.id),
            "records_extracted": run.records_extracted, "bucket": "raw-data", "files": outputs}


def ingest_fixture(payload):
    approved = authorize_fixture(payload)
    require_runtime_guard()
    from layer1_ingestion.core.config import get_settings
    require_local_storage(get_settings())
    from layer1_ingestion.core.database import get_db_context
    from layer1_ingestion.core import storage
    with get_db_context() as db:
        return _persist(approved, db, storage)
