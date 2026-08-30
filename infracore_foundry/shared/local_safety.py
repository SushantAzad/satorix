"""Fail-closed defaults for local development; no networking in this module."""
import os
from pathlib import Path


def local_safe_mode():
    # Missing, empty and misspelled flags remain safe. Disabling needs an explicit false.
    return os.environ.get("LOCAL_SAFE_MODE", "true").lower() != "false"


def require_external_approval(operation):
    if local_safe_mode():
        raise PermissionError("LOCAL SAFE MODE: disabled " + operation)


def check_connector(connector_name, config):
    if not local_safe_mode():
        return
    if connector_name != "CSVConnector":
        raise PermissionError("LOCAL SAFE MODE: connector disabled: " + connector_name)
    raw = str(config.get("file_path", ""))
    if not raw or "://" in raw or raw.startswith(("\\\\", "//")):
        raise PermissionError("LOCAL SAFE MODE: only approved local CSV fixtures are allowed")
    root = Path(__file__).resolve().parents[1] / "local_safe" / "fixtures"
    path = Path(raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise PermissionError("LOCAL SAFE MODE: CSV must be under local_safe/fixtures")
    if path.suffix.lower() != ".csv" or not path.is_file():
        raise PermissionError("LOCAL SAFE MODE: fixture must be an existing CSV file")
