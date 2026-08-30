import importlib.util
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import AsyncMock, patch
import unittest

fake = ModuleType("core.database")
fake.AsyncSessionLocal = None
web = ModuleType("fastapi")
class TestHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)
web.HTTPException = TestHTTPException
spec = importlib.util.spec_from_file_location("focused_under_test",
    Path(__file__).resolve().parents[2] / "layer3_ontology/storage/focused_store.py")
store = importlib.util.module_from_spec(spec)
with patch.dict("sys.modules", {"core.database": fake, "fastapi": web}):
    spec.loader.exec_module(store)


class FocusedStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_depth_cycles_and_missing_endpoints(self):
        nodes = [SimpleNamespace(object_type="company", primary_key=k, properties={"name": k})
                 for k in ("A", "B", "C")]
        def link(a, b):
            return SimpleNamespace(source_type="company", source_id=a,
                target_type="company", target_id=b, link_type="OWNS", properties={}, is_inferred=False)
        links = [link("A", "B"), link("B", "C"), link("C", "B"), link("A", "HIDDEN")]
        for depth, expected in [(1, 2), (2, 3)]:
            db = SimpleNamespace(execute=AsyncMock(side_effect=[
                SimpleNamespace(fetchall=lambda: nodes), SimpleNamespace(fetchall=lambda: links)]))
            context = AsyncMock()
            context.__aenter__.return_value = db
            with patch.object(store, "AsyncSessionLocal", return_value=context):
                result = await store.network("company", "A", depth, "tenant")
            self.assertEqual(len(result["nodes"]), expected)
            self.assertFalse(any(e["targetPK"] == "HIDDEN" for e in result["edges"]))
            for call in db.execute.call_args_list:
                self.assertEqual(call.args[1]["tenant"], "tenant")
                self.assertIn("client_id IN", str(call.args[0]))

    async def test_unknown_root_is_not_fabricated(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [])))
        context = AsyncMock()
        context.__aenter__.return_value = db
        with patch.object(store, "AsyncSessionLocal", return_value=context):
            with self.assertRaises(store.HTTPException) as error:
                await store.network("company", "missing", 2, "tenant")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
