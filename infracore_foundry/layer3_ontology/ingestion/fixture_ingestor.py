"""Manifest-only Layer 3 ingestion for the sealed company fixture."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _read_json(client, bucket: str, key: str, expected_sha256: str | None = None) -> Any:
    response = client.get_object(bucket, key)
    try:
        payload = response.read()
    finally:
        response.close(); response.release_conn()
    if expected_sha256 and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError(f"Processed fixture checksum mismatch: {key}")
    return json.loads(payload)


async def ingest_company_fixture(manifest_bucket: str, manifest_key: str) -> dict:
    from shared.fixture_operation import (
        CLIENT_ID, CONTRACT_VERSION, FIXTURE_ID, SOURCE_ID,
        authorize_fixture, require_runtime_guard,
    )
    from core.minio_client import minio_client
    from storage.object_data_funnel import object_data_funnel

    approved = authorize_fixture({"fixture_id": FIXTURE_ID})
    require_runtime_guard()
    expected_prefix = (
        f"local-company-investigation/{SOURCE_ID}/{approved.batch_id}/"
        f"{approved.batch_id}:company-investigation-fixture-v1/"
    )
    if manifest_bucket != "processed-data" or manifest_key != expected_prefix + "manifest.json":
        raise PermissionError("Only the deterministic processed fixture manifest is accepted")
    manifest = _read_json(minio_client.client, manifest_bucket, manifest_key)
    required = {
        "status": "completed", "fixture_id": FIXTURE_ID,
        "contract_version": CONTRACT_VERSION, "source_id": SOURCE_ID,
        "client_id": CLIENT_ID, "batch_id": approved.batch_id,
        "input_checksum": approved.input_checksum,
        "pipeline_version": "company-investigation-fixture-v1",
    }
    if any(manifest.get(key) != value for key, value in required.items()):
        raise ValueError("Processed manifest identity does not match the sealed fixture")
    files = {entry["kind"]: entry for entry in manifest.get("files", [])}
    if set(files) != {"entities", "relationships", "outcomes"}:
        raise ValueError("Processed manifest file set is incomplete")
    entities = _read_json(minio_client.client, files["entities"]["bucket"], files["entities"]["key"], files["entities"]["sha256"])
    relationships = _read_json(minio_client.client, files["relationships"]["bucket"], files["relationships"]["key"], files["relationships"]["sha256"])
    if len(entities) != files["entities"]["count"] or len(relationships) != files["relationships"]["count"]:
        raise ValueError("Processed manifest row counts do not match payloads")

    object_results = []
    for record in entities:
        if record.get("client_id") != CLIENT_ID or record.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("Entity record escaped the fixture tenant/contract")
        result = await object_data_funnel.write_object(
            object_type=record["object_type"], data=record["properties"],
            source=f"fixture:{SOURCE_ID}:{approved.batch_id}", actor="fixture_pipeline",
            client_id=CLIENT_ID,
        )
        if not result.success:
            raise RuntimeError("; ".join(result.errors))
        object_results.append(result)

    link_results = []
    for record in relationships:
        if record.get("client_id") != CLIENT_ID or record.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("Relationship record escaped the fixture tenant/contract")
        result = await object_data_funnel.write_link(
            link_type=record["link_type"], source_type=record["source_type"],
            source_id=record["source_id"], target_type=record["target_type"],
            target_id=record["target_id"], properties=record["properties"],
            actor="fixture_pipeline", client_id=CLIENT_ID,
        )
        if not result.success:
            raise RuntimeError("; ".join(result.errors))
        link_results.append(result)

    return {
        "status": "completed", "fixture_id": FIXTURE_ID, "client_id": CLIENT_ID,
        "batch_id": approved.batch_id, "objects_written": len(object_results),
        "links_written": len(link_results), "manifest_key": manifest_key,
    }
