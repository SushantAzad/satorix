"""Layer 2 adapter for the sealed synthetic company-investigation fixture."""
from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Any

PIPELINE_VERSION = "company-investigation-fixture-v1"
PROCESSED_BUCKET = "processed-data"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _valid_id(value: str, kind: str) -> bool:
    return re.fullmatch(rf"DEMO-{kind}-[0-9]{{3}}", value or "") is not None


def _relationship_signals(expected: dict) -> dict[str, dict]:
    """Build non-predictive review signals from the sealed relationship rules."""
    investigation = expected["initial"]["investigation"]
    pair_scores = expected["initial"]["pair_scores"]
    signals: dict[str, dict] = {}
    for pair, score in pair_scores.items():
        left, right = pair.split("|", 1)
        if score <= 0:
            continue
        for company_id, related_id in ((left, right), (right, left)):
            current = signals.get(company_id)
            if current is None or score > current["score"]:
                flags: list[str] = []
                if {company_id, related_id} == {investigation["company"], investigation["shared_director_companies"][0]}:
                    flags = ["SHARED_DIRECTOR", "SHARED_ADDRESS", "MULTIPLE_RELATIONSHIP_TYPES"]
                elif score == 1:
                    flags = ["SHARED_ADDRESS"]
                signals[company_id] = {
                    "name": expected["signal"]["name"],
                    "version": expected["signal"]["version"],
                    "score": score,
                    "maximum": expected["signal"]["maximum"],
                    "flags": flags,
                    "relatedCompanyIds": [related_id],
                    "interpretation": expected["signal"]["interpretation"],
                }
            elif score == current["score"] and related_id not in current["relatedCompanyIds"]:
                current["relatedCompanyIds"].append(related_id)
    return signals


def transform_rows(rows: dict[str, list[dict[str, Any]]], expected: dict) -> tuple[list[dict], list[dict], dict]:
    """Derive canonical entities/links from raw L1 records and verify the sealed oracle."""
    files = (
        "companies_initial.csv", "directors_initial.csv",
        "addresses_initial.csv", "directorships_initial.csv",
    )
    outcomes = {name: {"accepted": {}, "rejected": {}, "review": {}} for name in files}

    for name in files:
        for row in rows[name]:
            rid = row["source_record_id"]
            decision, value = "accepted", None
            if name == "companies_initial.csv":
                value = row["company_id"]
                if not _clean(row["company_name"]):
                    decision, value = "rejected", "missing_company_name"
                elif not value:
                    decision, value = "review", "missing_authoritative_company_id"
                elif not _valid_id(value, "C"):
                    decision, value = "rejected", "invalid_company_id"
            elif name == "directors_initial.csv":
                value = row["director_id"]
                if not _valid_id(value, "D"):
                    decision, value = "rejected", "invalid_director_id"
            elif name == "addresses_initial.csv":
                value = row["address_id"]
                if not _clean(row["address_text"]):
                    decision, value = "rejected", "missing_address_text"
                elif not _valid_id(value, "A"):
                    decision, value = "rejected", "invalid_address_id"
            else:
                value = f"DIRECTED|{row['director_id']}|{row['company_id']}"
                if row["director_id"] not in outcomes[files[1]]["accepted"].values():
                    decision, value = "rejected", "unknown_director_reference"
                elif row["company_id"] not in outcomes[files[0]]["accepted"].values():
                    decision, value = "rejected", "unknown_company_reference"
            outcomes[name][decision][rid] = value

    entities: dict[str, dict[str, dict]] = {"Company": {}, "Director": {}, "Address": {}}
    evidence: dict[str, list[str]] = {}
    source_locations: dict[str, dict] = {}
    for name, kind in zip(files[:3], entities):
        for line, row in enumerate(sorted(rows[name], key=lambda item: item["source_record_id"]), 2):
            rid = row["source_record_id"]
            source_locations[rid] = {"filename": name, "line": line}
            if rid not in outcomes[name]["accepted"]:
                continue
            key = outcomes[name]["accepted"][rid]
            evidence.setdefault(key, []).append(rid)
            if kind == "Company":
                value = {"name": _clean(row["company_name"]), "status": row["status"], "address_id": row["address_id"]}
            elif kind == "Director":
                value = {"name": _clean(row["director_name"])}
            else:
                value = {"normalizedAddress": _clean(row["address_text"]).casefold()}
            entities[kind].setdefault(key, value)

    links: list[dict] = []
    for line, row in enumerate(rows[files[3]], 2):
        rid = row["source_record_id"]
        source_locations[rid] = {"filename": files[3], "line": line}
        if rid in outcomes[files[3]]["accepted"]:
            director_id, company_id = row["director_id"], row["company_id"]
            links.append({
                "type": "DIRECTED", "source": director_id, "target": company_id,
                "evidence": [rid] + evidence[director_id] + evidence[company_id],
                "properties": {"appointedDate": row["appointed_date"]},
            })
    for company_id, properties in entities["Company"].items():
        address_id = properties["address_id"]
        links.append({
            "type": "REGISTERED_AT", "source": company_id, "target": address_id,
            "evidence": evidence[company_id] + evidence[address_id], "properties": {},
        })

    oracle = expected["initial"]
    comparable_links = [{k: link[k] for k in ("type", "source", "target", "evidence")} for link in links]
    if outcomes != oracle["outcomes"] or entities != oracle["canonical_entities"] or comparable_links != oracle["active_relationships"]:
        raise ValueError("Layer 2 fixture transformation diverged from the sealed contract")

    common = {
        "client_id": expected["client_id"], "source_id": expected["source_id"],
        "contract_version": expected["contract_version"],
    }
    relationship_signals = _relationship_signals(expected)
    entity_records: list[dict] = []
    for kind, values in entities.items():
        for key, value in values.items():
            object_type = kind.lower()
            properties = {**value, "synthetic": True, "riskScore": 0, "riskFlags": ["SYNTHETIC_FIXTURE"]}
            if kind == "Company":
                properties.update({"cin": key, "syntheticCompanyId": key})
                if key in relationship_signals:
                    properties["investigationSignal"] = relationship_signals[key]
            elif kind == "Director":
                properties.update({"din": key, "syntheticDirectorId": key})
            else:
                properties.update({"syntheticAddressId": key, "fullAddress": value["normalizedAddress"]})
            entity_records.append({
                **common, "object_type": object_type, "primary_key": key,
                "properties": properties, "evidence": [
                    {"source_record_id": rid, **source_locations[rid]} for rid in evidence[key]
                ],
            })

    address_keys = {key: value["normalizedAddress"] for key, value in entities["Address"].items()}
    relationship_records = []
    for link in links:
        is_directed = link["type"] == "DIRECTED"
        relationship_records.append({
            **common, "link_type": link["type"],
            "source_type": "director" if is_directed else "company",
            "source_id": link["source"],
            "target_type": "company" if is_directed else "address",
            "target_id": link["target"] if is_directed else address_keys[link["target"]],
            "synthetic_target_id": link["target"],
            "properties": {**link["properties"], "synthetic": True, "evidence": link["evidence"]},
            "evidence": [{"source_record_id": rid, **source_locations[rid]} for rid in link["evidence"]],
        })
    return entity_records, relationship_records, outcomes


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _put_json(client, bucket: str, key: str, value: Any) -> dict:
    payload = _json_bytes(value)
    client.put_object(bucket, key, io.BytesIO(payload), len(payload), content_type="application/json")
    return {"bucket": bucket, "key": key, "sha256": hashlib.sha256(payload).hexdigest(), "count": len(value) if isinstance(value, list) else 1}


def process_fixture() -> dict:
    """Read sealed Layer 1 Parquets and publish the deterministic Layer 2 manifest."""
    from shared.fixture_operation import (
        CLIENT_ID, CONTRACT_VERSION, FILES, FIXTURE_ID, SOURCE_ID,
        authorize_fixture, require_local_storage, require_runtime_guard,
    )
    from layer1_ingestion.core.config import get_settings
    from layer1_ingestion.core.storage import get_minio_client
    import pyarrow.parquet as pq

    approved = authorize_fixture({"fixture_id": FIXTURE_ID})
    require_runtime_guard()
    require_local_storage(get_settings())
    expected_path = approved.paths[0].parent / "expected_results.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    client = get_minio_client()
    rows: dict[str, list[dict]] = {}
    raw_prefix = f"local-company-investigation/{SOURCE_ID}/{approved.batch_id}"
    for name in FILES:
        key = f"{raw_prefix}/{name[:-4]}.parquet"
        response = client.get_object("raw-data", key)
        try:
            frame = pq.read_table(io.BytesIO(response.read())).to_pandas().fillna("")
        finally:
            response.close(); response.release_conn()
        rows[name] = [{k: v for k, v in record.items() if not str(k).startswith("_")} for record in frame.to_dict(orient="records")]

    entity_records, relationship_records, outcomes = transform_rows(rows, expected)
    dataset_version = f"{approved.batch_id}:{PIPELINE_VERSION}"
    prefix = f"local-company-investigation/{SOURCE_ID}/{approved.batch_id}/{dataset_version}"
    entities_file = _put_json(client, PROCESSED_BUCKET, f"{prefix}/entities.json", entity_records)
    entities_file.update({"kind": "entities", "schema": "fixture-ontology-entity/v1"})
    relationships_file = _put_json(client, PROCESSED_BUCKET, f"{prefix}/relationships.json", relationship_records)
    relationships_file.update({"kind": "relationships", "schema": "fixture-ontology-link/v1"})
    outcomes_file = _put_json(client, PROCESSED_BUCKET, f"{prefix}/outcomes.json", outcomes)
    outcomes_file.update({"kind": "outcomes", "schema": "fixture-row-outcome/v1"})
    manifest = {
        "status": "completed", "operation": "initial", "fixture_id": FIXTURE_ID,
        "contract_version": CONTRACT_VERSION, "dataset_id": expected["dataset_id"],
        "source_id": SOURCE_ID, "client_id": CLIENT_ID, "batch_id": approved.batch_id,
        "input_checksum": approved.input_checksum, "pipeline_version": PIPELINE_VERSION,
        "dataset_version": dataset_version, "counts": expected["initial"]["counts"],
        "files": [entities_file, relationships_file, outcomes_file],
    }
    manifest_key = f"{prefix}/manifest.json"
    _put_json(client, PROCESSED_BUCKET, manifest_key, manifest)
    return {"status": "completed", "fixture_id": FIXTURE_ID, "manifest_bucket": PROCESSED_BUCKET, "manifest_key": manifest_key, **manifest}
