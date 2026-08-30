"""Static regression checks for the Safe/Development mode boundary."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ControllerPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((ROOT / "compose.local-safe.json").read_text())
        cls.development = json.loads((ROOT / "compose.development.json").read_text())
        cls.unrestricted = json.loads((ROOT / "compose.unrestricted.json").read_text())

    def test_project_names_are_distinct(self):
        self.assertEqual(self.base["name"], "satorix-local-safe")
        self.assertEqual(self.development["name"], "satorix-development")
        self.assertEqual(self.unrestricted["name"], "satorix-unrestricted")

    def test_development_uses_contained_launcher_for_every_api(self):
        for number in range(1, 7):
            service = self.development["services"][f"layer{number}-api"]
            self.assertEqual(service["entrypoint"][1], "/opt/satorix-safe/development_launch.py")
            self.assertEqual(service["environment"]["DEVELOPMENT_MODE"], "true")
            self.assertEqual(service["environment"]["LOCAL_SAFE_MODE"], "true")

    def test_runtime_network_has_no_masquerade(self):
        network = self.base["networks"]["local-safe"]
        self.assertFalse(network["internal"])
        self.assertEqual(
            network["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"],
            "false",
        )
        for service in self.base["services"].values():
            self.assertEqual(service["pull_policy"], "never")
            self.assertEqual(service["dns"], ["127.0.0.1"])

    def test_forbidden_background_services_remain_absent(self):
        forbidden = {
            "airflow-init", "airflow-webserver", "airflow-scheduler", "airflow-worker",
            "streaming-worker", "ollama", "ollama-init",
        }
        self.assertTrue(forbidden.isdisjoint(self.base["services"]))
        self.assertTrue(forbidden.isdisjoint(self.development["services"]))

    def test_development_launcher_keeps_egress_guard_without_read_only_middleware(self):
        source = (ROOT / "local_safe" / "development_launch.py").read_text()
        self.assertIn("install()", source)
        self.assertIn('DEVELOPMENT_MODE", ""', source)
        self.assertNotIn("ReadOnlyLocalMiddleware", source)

    def test_unrestricted_explicitly_disables_every_api_safe_gate(self):
        for number in range(1, 7):
            service = self.unrestricted["services"][f"layer{number}-api"]
            self.assertEqual(service["environment"]["LOCAL_SAFE_MODE"], "false")
        for service in ("airflow-init", "airflow-webserver", "airflow-scheduler",
                        "airflow-worker", "streaming-worker"):
            self.assertEqual(
                self.unrestricted["services"][service]["environment"]["LOCAL_SAFE_MODE"],
                "false",
            )

    def test_legacy_compose_has_no_global_container_names(self):
        self.assertNotIn("container_name:", (ROOT / "docker-compose.yml").read_text())


if __name__ == "__main__":
    unittest.main()
