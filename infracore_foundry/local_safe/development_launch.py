"""Development launcher: offline by default; focused Gemini has explicit opt-in egress."""
import importlib
import os
import sys

from runtime import install

if os.environ.get("DEVELOPMENT_MODE", "").lower() != "true":
    raise RuntimeError("Contained development launcher requires DEVELOPMENT_MODE=true")

# Retain LOCAL_SAFE_MODE=true so connector, LLM, model and background-worker gates
# stay closed. Unlike launch.py, this launcher does not attach read-only middleware.
install()
module_name, app_name = sys.argv[1].split(":", 1)
app = getattr(importlib.import_module(module_name), app_name)

import uvicorn  # noqa: E402 -- install the egress guard before application imports

uvicorn.run(app, host="0.0.0.0", port=int(sys.argv[2]), workers=1, loop="asyncio")
