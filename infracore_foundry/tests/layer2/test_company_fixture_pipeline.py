import csv
import json
import unittest
from pathlib import Path

from layer2_pipeline.fixtures.company_investigation import transform_rows


ROOT = Path(__file__).resolve().parents[2] / "local_safe" / "fixtures" / "company_investigation_v1"
FILES = (
    "companies_initial.csv", "directors_initial.csv",
    "addresses_initial.csv", "directorships_initial.csv",
)


class CompanyFixturePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))
        cls.rows = {}
        for name in FILES:
            with (ROOT / name).open(encoding="utf-8", newline="") as stream:
                cls.rows[name] = list(csv.DictReader(stream))

    def test_derives_contract_entities_relationships_and_outcomes(self):
        entities, relationships, outcomes = transform_rows(self.rows, self.expected)
        self.assertEqual(len(entities), 11)
        self.assertEqual(len(relationships), 9)
        self.assertEqual(outcomes, self.expected["initial"]["outcomes"])
        self.assertEqual({item["object_type"] for item in entities}, {"company", "director", "address"})
        self.assertEqual({item["client_id"] for item in entities}, {"LOCAL_SYNTHETIC_DEMO"})

    def test_preserves_synthetic_ids_and_resolves_address_natural_keys(self):
        entities, relationships, _ = transform_rows(self.rows, self.expected)
        companies = {item["primary_key"]: item for item in entities if item["object_type"] == "company"}
        self.assertEqual(companies["DEMO-C-001"]["properties"]["cin"], "DEMO-C-001")
        registered = [item for item in relationships if item["link_type"] == "REGISTERED_AT"]
        self.assertEqual(len(registered), 5)
        self.assertTrue(all(item["target_id"].startswith("synthetic site") for item in registered))
        self.assertTrue(all(item["synthetic_target_id"].startswith("DEMO-A-") for item in registered))

    def test_rejects_transformation_drift(self):
        changed = {name: [dict(row) for row in values] for name, values in self.rows.items()}
        changed["companies_initial.csv"][0]["company_name"] = "SYNTHETIC Drifted Name"
        with self.assertRaisesRegex(ValueError, "diverged"):
            transform_rows(changed, self.expected)

    def test_publishes_relationship_review_signal_without_inflating_risk(self):
        entities, _, _ = transform_rows(self.rows, self.expected)
        amberbridge = next(item for item in entities if item["primary_key"] == "DEMO-C-001")
        properties = amberbridge["properties"]
        self.assertEqual(properties["riskScore"], 0)
        self.assertEqual(properties["investigationSignal"]["score"], 3)
        self.assertEqual(properties["investigationSignal"]["relatedCompanyIds"], ["DEMO-C-002"])
        self.assertIn("MULTIPLE_RELATIONSHIP_TYPES", properties["investigationSignal"]["flags"])


if __name__ == "__main__":
    unittest.main()
