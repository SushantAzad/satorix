"""Explicit safe API launcher; guard failure exits before importing the application."""
import importlib
import sys
from runtime import install, ReadOnlyLocalMiddleware

install()
module_name, app_name = sys.argv[1].split(":", 1)
app = getattr(importlib.import_module(module_name), app_name)
app.add_middleware(
    ReadOnlyLocalMiddleware,
    fixture_import=(module_name == "layer1_ingestion.api.app"),
)
import uvicorn  # noqa: E402 -- install the egress guard before application imports
uvicorn.run(app, host="0.0.0.0", port=int(sys.argv[2]), workers=1, loop="asyncio")
