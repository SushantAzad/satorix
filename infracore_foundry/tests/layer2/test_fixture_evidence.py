import os
import unittest
from unittest.mock import patch
from shared.fixture_evidence import read_fixture_evidence
from shared.fixture_operation import CLIENT_ID


class FixtureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LOCAL_SAFE_MODE": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_source_row_and_provenance(self):
        result = read_fixture_evidence("RROW-001", CLIENT_ID)
        self.assertEqual(result["filename"], "directorships_initial.csv")
        self.assertEqual(result["dataRow"], 1)
        self.assertEqual(result["fields"]["company_id"], "DEMO-C-001")
        self.assertEqual(len(result["fileSha256"]), 64)

    def test_cross_tenant_denied_before_read(self):
        with patch("shared.fixture_evidence.authorize_fixture") as authorize:
            with self.assertRaises(PermissionError):
                read_fixture_evidence("RROW-001", "PLATFORM_GLOBAL")
            authorize.assert_not_called()

    def test_invalid_and_missing_ids(self):
        for value in ("../.env", "https://example.com", "RROW-999", ""):
            with self.subTest(value=value), self.assertRaises(LookupError):
                read_fixture_evidence(value, CLIENT_ID)

    def test_not_available_outside_contained_modes(self):
        with patch.dict(os.environ, {"LOCAL_SAFE_MODE": "false"}), self.assertRaises(PermissionError):
            read_fixture_evidence("RROW-001", CLIENT_ID)

    def test_integrity_failure_is_not_swallowed(self):
        with patch("shared.fixture_evidence.authorize_fixture", side_effect=PermissionError("tampered")), self.assertRaises(PermissionError):
            read_fixture_evidence("RROW-001", CLIENT_ID)
