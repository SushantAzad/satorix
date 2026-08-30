"""Closed registry for the initial company fixture operation; no I/O beyond local reads."""
import csv
import base64
import binascii
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re

FIXTURE_ID = "company_investigation_v1"
IMPORT_PATH = "/api/v1/fixtures/import"
CLIENT_ID = "LOCAL_SYNTHETIC_DEMO"
SOURCE_ID = "local-synthetic-company-fixtures-v1"
CONTRACT_VERSION = "local-company-investigation/v1"
FILES = (
    "companies_initial.csv", "directors_initial.csv",
    "addresses_initial.csv", "directorships_initial.csv",
)
# Content changes require deliberate registry review; no caller-supplied checksums.
_DIGESTS = {
    "companies_initial.csv": "43caabf26d6abed1265a3e13f8dbb95a0ce97de9f460c4059ac0d0ac4585c1ec",
    "directors_initial.csv": "7c7feaa34f9cb883ae8928e4c0a449a7adbb819f54c46bc93626d96e28baa196",
    "addresses_initial.csv": "1512abd1f7827ed41af23a706ae24b32eea353943a0db09d2e7fc951ad673100",
    "directorships_initial.csv": "fab6c110e69ae4acf3ab9b3a7a5f8da9e738f13997429f04c8059c0aff337e16",
    "expected_results.json": "3e3d12752ef3bc3d2f3eaf4016600edd33cca055a3f0d6bec39fb2efb2a13775",
    "CONTRACT.md": "f3e7fbcbf3912ac55a78190326b887ba94b159ea46986caed373c08be9289e42",
}
_SEAL = object()


def require_safe_mode():
    if os.environ.get("LOCAL_SAFE_MODE", "").lower() != "true":
        raise PermissionError("Fixture import requires explicit LOCAL_SAFE_MODE=true")


def _root():
    return Path(__file__).resolve().parents[1] / "local_safe" / "fixtures"


def _contained_file(root, name):
    # Names come only from the registry. Check resolved ancestors and every file,
    # including junction/symlink escapes; never resolve a caller-supplied path.
    original_root = root.absolute()
    root = root.resolve(strict=True)
    if root != original_root:
        raise PermissionError("Fixture root may not be redirected")
    directory = (root / FIXTURE_ID).resolve(strict=True)
    directory.relative_to(root)
    if directory != root / FIXTURE_ID:
        raise PermissionError("Fixture directory may not be redirected")
    path = (directory / name).resolve(strict=True)
    path.relative_to(directory)
    if path != directory / name or not path.is_file():
        raise PermissionError("Fixture file may not be redirected")
    return path


@dataclass(frozen=True)
class ApprovedFixture:
    paths: tuple
    input_checksum: str
    batch_id: str
    _identities: frozenset
    _seal: object

    def demo_identity(self, entity_type, value):
        """Workflow-scoped identity descriptor, never a CIN/DIN or ontology object."""
        require_safe_mode()
        prefixes = {"Company": "C", "Director": "D", "Address": "A"}
        if (self._seal is not _SEAL or entity_type not in prefixes or
                not isinstance(value, str) or
                not re.fullmatch(r"DEMO-" + prefixes[entity_type] + r"-[0-9]{3}", value) or
                (entity_type, value) not in self._identities):
            raise PermissionError("Identity is not approved for this synthetic fixture")
        return {"scheme": "local-demo-v1", "synthetic": True,
                "entity_type": entity_type, "value": value, "client_id": CLIENT_ID}


def authorize_fixture(payload):
    require_safe_mode()
    if not isinstance(payload, dict) or set(payload) != {"fixture_id"} or payload["fixture_id"] != FIXTURE_ID:
        raise PermissionError("Only the registered fixture identifier is accepted")
    try:
        root = _root()
        contents = {}
        paths = {}
        for name, digest in _DIGESTS.items():
            path = _contained_file(root, name)
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise PermissionError("Approved fixture content/contract changed")
            contents[name], paths[name] = content, path
        expected = json.loads(contents["expected_results.json"])
        if (expected["contract_version"] != CONTRACT_VERSION or
                expected["source_id"] != SOURCE_ID or expected["client_id"] != CLIENT_ID):
            raise PermissionError("Unexpected fixture contract")
        descriptor = b"".join(
            name.encode() + b"\0" + hashlib.sha256(contents[name]).hexdigest().encode() + b"\n"
            for name in sorted(FILES)
        )
        checksum = hashlib.sha256(descriptor).hexdigest()
        batch = hashlib.sha256((CLIENT_ID + "\0" + SOURCE_ID + "\0" + checksum).encode()).hexdigest()
        identities = frozenset((kind, key) for kind, values in expected["initial"]["canonical_entities"].items() for key in values)
        return ApprovedFixture(tuple(paths[name] for name in FILES), checksum, batch, identities, _SEAL)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PermissionError("Fixture is missing, outside its directory, or invalid") from exc


def expected_rows(path):
    """Read only an already authorized path; used to verify connector preservation."""
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def require_local_storage(settings):
    require_safe_mode()
    expected = {
        "postgres_host": "postgres", "postgres_port": 5432,
        "postgres_db": "satorix_safe", "postgres_user": "satorix_safe",
        "postgres_password": "LocalFixturePasswordOnly123",
        "minio_endpoint": "minio:9000", "minio_secure": False,
        "minio_raw_bucket": "raw-data", "minio_access_key": "localfixture",
        "minio_secret_key": "LocalFixtureMinioOnly123",
        "api_key": "local-fixture-api-key-not-production",
    }
    if any(getattr(settings, key, None) != value for key, value in expected.items()):
        raise PermissionError("Fixture import requires the dedicated local safe storage settings")
    try:
        key = base64.b64decode(os.environ.get("ENCRYPTION_KEY", ""), validate=True)
        if len(key) != 32:
            raise ValueError("Invalid key size")
    except (ValueError, binascii.Error) as exc:
        raise PermissionError("Fixture source registration requires a valid 32-byte local encryption key") from exc


def require_runtime_guard():
    import sys
    guard = sys.modules.get("runtime") or sys.modules.get("local_safe.runtime")
    if guard is None or not getattr(guard, "_installed", False):
        raise PermissionError("Fixture writes require the Local Safe launcher egress guard")
