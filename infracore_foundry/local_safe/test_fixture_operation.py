"""Offline tests: actual CSV extraction, mocked PostgreSQL/MinIO; no services."""
import base64
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import fixture_operation as policy  # noqa: E402 -- standalone test entry point
from runtime import ReadOnlyLocalMiddleware  # noqa: E402

_spec = importlib.util.spec_from_file_location("fixture_import_under_test", ROOT / "layer1_ingestion/sync/fixture_import.py")
operation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(operation)

PAYLOAD = {"fixture_id": policy.FIXTURE_ID}


@contextmanager
def l1_dependencies():
    """Isolate missing MinIO dependency and eager connector-package imports.

    Load the actual CSV/base connector, models and registry; mock only storage.
    No claim that the full application package imports on this host.
    """
    stubs = {}
    for name, path in (
        ("layer1_ingestion.connectors", ROOT / "layer1_ingestion/connectors"),
        ("layer1_ingestion.core", ROOT / "layer1_ingestion/core"),
    ):
        module = ModuleType(name)
        module.__path__ = [str(path)]
        stubs[name] = module
    storage = ModuleType("layer1_ingestion.core.storage")
    for name in ("upload_parquet", "generate_object_path", "get_minio_client", "object_exists"):
        setattr(storage, name, MagicMock(name=name))
    stubs[storage.__name__] = storage
    saved = {name: sys.modules.get(name) for name in stubs}
    before = set(sys.modules)
    sys.modules.update(stubs)
    try:
        yield storage
    finally:
        for name in set(sys.modules) - before:
            if name.startswith("layer1_ingestion."):
                del sys.modules[name]
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def run_inline(coroutine):
    """These ASGI unit calls have no asynchronous I/O; avoid Windows socketpair."""
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coroutine.close()
    raise AssertionError("Offline ASGI test unexpectedly requested asynchronous I/O")


class FixturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LOCAL_SAFE_MODE": "true", "ENCRYPTION_KEY": base64.b64encode(b"x" * 32).decode()})
        self.env.start()
        self.addCleanup(self.env.stop)
        # An accidental live DNS/connect attempt is a test failure, even to local services.
        for target in ("socket.getaddrinfo", "socket.socket.connect", "socket.socket.sendto"):
            guard = patch(target, side_effect=AssertionError("Network is forbidden in these tests"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_approved_registry_contract_and_batch_identity(self):
        approved = policy.authorize_fixture(PAYLOAD)
        self.assertEqual(tuple(p.name for p in approved.paths), policy.FILES)
        for path in approved.paths:
            self.assertEqual(path.parent, (policy._root() / policy.FIXTURE_ID).resolve())
        spec = importlib.util.spec_from_file_location("fixture_consistency_oracle", approved.paths[0].parent / "test_consistency.py")
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        expected = json.loads((approved.paths[0].parent / "expected_results.json").read_text())
        self.assertEqual((approved.input_checksum, approved.batch_id), oracle.content_identity(policy.FILES, expected))

    def test_paths_urls_unc_unknown_and_extra_configuration_denied(self):
        for value in ("../company_investigation_v1", str(ROOT), "/tmp/fixture.csv",
                      "http://unapproved.invalid/a.csv", "https://unapproved.invalid/a.csv",
                      "\\\\unapproved\\share\\a.csv", "//unapproved/share/a.csv", "unknown",
                      "company_investigation_v1/companies_initial.csv", None, []):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                policy.authorize_fixture({"fixture_id": value})
        for key in ("path", "url", "connector_type", "config", "destination", "client_id", "source_id"):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                policy.authorize_fixture({**PAYLOAD, key: "unapproved"})

    def test_containment_and_contract_tampering_denied(self):
        with self.assertRaises((PermissionError, ValueError)):
            policy._contained_file(policy._root(), "../../test_policy.py")
        with patch.object(Path, "read_bytes", return_value=b"altered"):
            with self.assertRaises(PermissionError):
                policy.authorize_fixture(PAYLOAD)
        original = Path.resolve
        def redirected(path, *args, **kwargs):
            if path.name == policy.FIXTURE_ID:
                return ROOT  # Model a symlink/junction escaping the approved subtree.
            return original(path, *args, **kwargs)
        with patch.object(Path, "resolve", redirected), self.assertRaises(PermissionError):
            policy.authorize_fixture(PAYLOAD)

    def test_safe_mode_is_required_for_authorization_and_identity(self):
        approved = policy.authorize_fixture(PAYLOAD)
        for flag in ("false", "", "tru", "0"):
            with patch.dict(os.environ, {"LOCAL_SAFE_MODE": flag}):
                with self.assertRaises(PermissionError):
                    policy.authorize_fixture(PAYLOAD)
                with self.assertRaises(PermissionError):
                    approved.demo_identity("Company", "DEMO-C-001")
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(PermissionError):
            policy.authorize_fixture(PAYLOAD)

    def test_demo_identity_is_scoped_and_not_a_government_identifier(self):
        approved = policy.authorize_fixture(PAYLOAD)
        for kind, value in (("Company", "DEMO-C-001"), ("Director", "DEMO-D-001"), ("Address", "DEMO-A-001")):
            identity = approved.demo_identity(kind, value)
            self.assertTrue(identity["synthetic"])
            self.assertEqual(identity["scheme"], "local-demo-v1")
            self.assertEqual(identity["value"], value)
        # Format-shaped strings are invented here, not real government records.
        for value in ("U00000ZZ2000PTC000000", "00000000", "DEMO-C-999", "DEMO-C-1", "demo-c-001", "DEMO-D-001", "DEMO-C-001/..", "", None):
            with self.subTest(value=value), self.assertRaises(PermissionError):
                approved.demo_identity("Company", value)
        forged = policy.ApprovedFixture(approved.paths, approved.input_checksum, approved.batch_id, approved._identities, object())
        with self.assertRaises(PermissionError):
            forged.demo_identity("Company", "DEMO-C-001")

    def test_global_identity_validators_unchanged(self):
        spec = importlib.util.spec_from_file_location("existing_indian_types", ROOT / "layer3_ontology/semantic/properties/indian_types.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.CIN_Type.validate("DEMO-C-001")
        with self.assertRaises(ValueError):
            module.DIN_Type.validate("DEMO-D-001")

    def test_destination_is_exact_safe_environment(self):
        compose = json.loads((ROOT / "compose.local-safe.json").read_text())
        env = compose["services"]["layer1-api"]["environment"]
        settings = SimpleNamespace(**{key.lower(): value for key, value in env.items()})
        settings.postgres_port = int(settings.postgres_port)
        settings.minio_secure = False
        policy.require_local_storage(settings)
        for key, value in (("postgres_host", "localhost"), ("postgres_db", "production"),
                           ("postgres_user", "other"), ("minio_endpoint", "https://unapproved.invalid"),
                           ("minio_raw_bucket", "other"), ("api_key", "")):
            with patch.object(settings, key, value), self.assertRaises(PermissionError):
                policy.require_local_storage(settings)
        with patch.dict(os.environ, {"ENCRYPTION_KEY": env["ENCRYPTION_KEY"]}):
            policy.require_local_storage(settings)
        with patch.dict(os.environ, {"ENCRYPTION_KEY": "bm90LTMyLWJ5dGVz"}), self.assertRaises(PermissionError):
            policy.require_local_storage(settings)

    def test_guard_required_before_storage_imports(self):
        with patch.object(policy, "require_runtime_guard", side_effect=PermissionError("no guard")):
            # operation has its own imported reference.
            with patch.object(operation, "require_runtime_guard", side_effect=PermissionError("no guard")):
                with self.assertRaises(PermissionError):
                    operation.ingest_fixture(PAYLOAD)

    def test_actual_csv_extraction_preserves_raw_records_and_provenance(self):
        approved = policy.authorize_fixture(PAYLOAD)
        with l1_dependencies():
            frames = operation._extract_frames(approved, "source-test", "run-test")
        self.assertEqual(sum(len(frame) for _, frame in frames), 24)
        for name, frame in frames:
            original = policy.expected_rows(next(p for p in approved.paths if p.name == name))
            self.assertEqual(frame[list(original[0])].to_dict(orient="records"), original)
            self.assertEqual(frame["_source_row_number"].tolist(), list(range(2, len(frame) + 2)))
            self.assertEqual(set(frame["_source_filename"]), {name})
            self.assertEqual(set(frame["_client_id"]), {policy.CLIENT_ID})
            self.assertEqual(set(frame["_batch_id"]), {approved.batch_id})
        companies = frames[0][1].set_index("source_record_id")
        self.assertIsNone(json.loads(companies.loc["CROW-009", "_demo_identities"])["company_id"])
        self.assertIsNone(json.loads(companies.loc["CROW-011", "_demo_identities"])["company_id"])

    def test_external_connector_policy_is_not_relaxed(self):
        from shared.local_safety import check_connector
        approved = policy.authorize_fixture(PAYLOAD)
        for connector in ("RestAPIConnector", "RESTAPIConnector", "S3Connector", "PostgreSQLConnector"):
            with self.assertRaises(PermissionError):
                check_connector(connector, {"file_path": str(approved.paths[0])})

    def test_middleware_exception_is_exact_and_opt_in(self):
        async def request(body, path=policy.IMPORT_PATH, method="POST", enabled=True, query=b""):
            messages, called = [], []
            async def handler(scope, receive, send):
                called.append((await receive())["body"])
            async def receive():
                return {"type": "http.request", "body": body}
            async def send(message):
                messages.append(message)
            await ReadOnlyLocalMiddleware(handler, fixture_import=enabled)(
                {"type": "http", "path": path, "method": method, "query_string": query}, receive, send)
            return called, messages
        body = json.dumps(PAYLOAD).encode()
        called, _ = run_inline(request(body))
        self.assertEqual(called, [body])
        cases = [dict(enabled=False), dict(query=b"url=bad"), dict(method="PUT"),
                 dict(path=policy.IMPORT_PATH + "/"), dict(path="/api/v1/sources/a/sync"),
                 dict(path="/api/v1/webhooks/a"), dict(path="/api/v1/llm/test")]
        for options in cases:
            called, messages = run_inline(request(body, **options))
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 403)
        for invalid in (b"{}", b"not json", b"x" * 1025, b'{"fixture_id":"unknown"}', b'{"fixture_id":"company_investigation_v1","connector_type":"rest_api"}'):
            called, messages = run_inline(request(invalid))
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 403)
        with patch.dict(os.environ, {"LOCAL_SAFE_MODE": "false"}):
            called, messages = run_inline(request(body))
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 403)

    def persistence_setup(self, storage):
        from sqlalchemy.engine import make_url
        db = MagicMock()
        db.get_bind.return_value.url = make_url("postgresql://satorix_safe:LocalFixturePasswordOnly123@postgres:5432/satorix_safe")
        db.query.return_value.filter.return_value.first.return_value = None
        storage.get_minio_client.return_value = SimpleNamespace(_base_url=SimpleNamespace(_url=urlsplit("http://minio:9000")))
        storage.object_exists.return_value = True
        return db

    def test_source_run_and_uploads_use_existing_l1_components(self):
        approved = policy.authorize_fixture(PAYLOAD)
        with l1_dependencies() as storage:
            db = self.persistence_setup(storage)
            result = operation._persist(approved, db, storage)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["records_extracted"], 24)
            self.assertEqual(result["bucket"], "raw-data")
            self.assertEqual(storage.upload_parquet.call_count, 4)
            for call in storage.upload_parquet.call_args_list:
                self.assertEqual(call.args[1], "raw-data")
                self.assertTrue(call.args[2].startswith("local-company-investigation/" + policy.SOURCE_ID + "/" + approved.batch_id + "/"))
            objects = [c.args[0] for c in db.add.call_args_list]
            self.assertEqual({type(obj).__name__ for obj in objects}, {"DataSource", "SyncState", "SyncRun"})
            self.assertIn("pg_advisory_xact_lock", str(db.execute.call_args.args[0]))

    def test_storage_error_is_failed_not_empty_success(self):
        with l1_dependencies() as storage:
            db = self.persistence_setup(storage)
            storage.upload_parquet.side_effect = RuntimeError("simulated local failure")
            with self.assertRaises(RuntimeError):
                operation._persist(policy.authorize_fixture(PAYLOAD), db, storage)
            runs = [c.args[0] for c in db.add.call_args_list if type(c.args[0]).__name__ == "SyncRun"]
            self.assertEqual(runs[0].status, "failed")

    def test_cached_external_clients_are_rejected_before_writes(self):
        with l1_dependencies() as storage:
            db = self.persistence_setup(storage)
            storage.get_minio_client.return_value._base_url._url = urlsplit("http://unapproved.invalid:9000")
            with self.assertRaises(PermissionError):
                operation._persist(policy.authorize_fixture(PAYLOAD), db, storage)
            db.execute.assert_not_called()
            storage.upload_parquet.assert_not_called()

    def test_completed_batch_reuses_records_without_uploading(self):
        from uuid import NAMESPACE_URL, uuid5
        approved = policy.authorize_fixture(PAYLOAD)
        source_id = uuid5(NAMESPACE_URL, policy.CLIENT_ID + ":" + policy.SOURCE_ID)
        source = SimpleNamespace(id=source_id, client_id=policy.CLIENT_ID, source_name=policy.SOURCE_ID,
                                 source_type="csv", environment="local-safe")
        run = SimpleNamespace(id="prior-run", source_id=source_id, status="completed", records_extracted=24)
        with l1_dependencies() as storage:
            db = self.persistence_setup(storage)
            db.query.return_value.filter.return_value.first.side_effect = [source, run]
            result = operation._persist(approved, db, storage)
            self.assertEqual(result["status"], "already_applied")
            self.assertEqual(result["run_id"], "prior-run")
            db.add.assert_not_called()
            storage.upload_parquet.assert_not_called()
            db.query.return_value.filter.return_value.first.side_effect = [source, run]
            storage.object_exists.return_value = False
            with self.assertRaises(RuntimeError):
                operation._persist(approved, db, storage)


if __name__ == "__main__":
    unittest.main(verbosity=2)
