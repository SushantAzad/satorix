"""Offline policy tests; rejected destinations never reach DNS or a socket."""
import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import runtime

from runtime import check_host, check_destination, ReadOnlyLocalMiddleware


class PolicyTests(unittest.TestCase):
    def test_unknown_hosts_and_addresses_are_denied(self):
        for host in ("unapproved.invalid", "host.docker.internal", "169.254.169.254",
                     "192.0.2.1", "10.0.0.1", "postgres.unapproved.invalid"):
            with self.assertRaises(PermissionError):
                check_host(host)
            with self.assertRaises(PermissionError):
                check_destination((host, 443))

    def test_only_exact_local_services_and_ports_allowed(self):
        check_host("postgres")
        check_destination(("postgres", 5432))
        check_destination(("layer6-api", 8006))
        with self.assertRaises(PermissionError):
            check_destination(("postgres", 443))

    def test_actions_blocked_before_handler(self):
        async def run(path, method):
            events = []
            async def handler(scope, receive, send):
                raise AssertionError("Blocked handler must never execute")
            async def send(event):
                events.append(event)
            await ReadOnlyLocalMiddleware(handler)(
                {"type": "http", "path": path, "method": method}, None, send)
            self.assertEqual(events[0]["status"], 403)
        for path, method in (("/api/v1/sources/a/sync", "POST"),
                             ("/api/v1/webhooks/a", "POST"),
                             ("/api/v1/operational/llm/status", "GET")):
            asyncio.run(run(path, method))

    def test_actual_audit_events_without_network(self):
        # Install with DNS mocked; emit genuine CPython audit events directly.
        import sys
        with patch.object(runtime.socket, "getaddrinfo", return_value=[]):
            runtime.install()
            with self.assertRaises(PermissionError):
                sys.audit("socket.getaddrinfo", "unapproved.invalid", 443, 0, 0, 0)
            with self.assertRaises(PermissionError):
                sys.audit("socket.connect", None, ("192.0.2.1", 443))
            with self.assertRaises(PermissionError):
                sys.audit("socket.sendto", None, b"blocked", ("192.0.2.1", 53))

    def test_late_service_resolution(self):
        with patch.object(runtime.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("192.0.2.25", 0))]):
            runtime._audit("socket.getaddrinfo", ("layer6-api", 8006, 0, 0, 0))
        runtime.check_destination(("192.0.2.25", 8006))
        with self.assertRaises(PermissionError):
            runtime.check_destination(("192.0.2.25", 443))
        runtime._addresses.pop("192.0.2.25", None)

    def test_fixture_policy(self):
        module_path = Path(__file__).resolve().parents[1] / "shared" / "local_safety.py"
        spec = importlib.util.spec_from_file_location("local_safety_test", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture = Path(__file__).parent / "fixtures" / "companies.csv"
        module.check_connector("CSVConnector", {"file_path": str(fixture)})
        for name, path in (("RestAPIConnector", str(fixture)),
                           ("CSVConnector", "https://unapproved.invalid/test.csv"),
                           ("CSVConnector", str(Path(__file__))),
                           ("CSVConnector", "//unapproved/share/test.csv")):
            with self.assertRaises(PermissionError):
                module.check_connector(name, {"file_path": path})


if __name__ == "__main__":
    unittest.main()
