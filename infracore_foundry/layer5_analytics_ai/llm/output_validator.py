"""
Validates LLM structured extraction outputs before writing to ontology.
Type 2 workflows (structured extraction) must pass validation or be flagged.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

REGULATORY_ACTION_SCHEMA = {
    "entity_name": str,
    "entity_type": str,
    "regulator": str,
    "action_type": str,
    "action_date": str,
    "penalty_amount_inr": (float, int, type(None)),
    "status": str,
    "summary": str,
}

VALID_STATUSES = {"Ongoing", "Resolved", "Appealed", "Dismissed"}
VALID_REGULATORS = {"SEBI", "RBI", "ED", "NHAI", "NCLT", "MCA", "CBI", "EOW", "SFIO"}


def validate_regulatory_action(raw_json: str) -> tuple[Optional[dict], list[str]]:
    """
    Parse and validate LLM-extracted regulatory action.
    Returns (validated_dict, errors). If errors is non-empty the output should NOT be written.
    """
    errors: list[str] = []
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, [f"JSON parse error: {exc}"]

    for field, expected_type in REGULATORY_ACTION_SCHEMA.items():
        val = data.get(field)
        if val is not None:
            if not isinstance(val, expected_type):
                errors.append(f"Field '{field}' type mismatch: expected {expected_type}, got {type(val)}")

    # Date sanity check
    date_str = data.get("action_date")
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt.year < 1990 or dt.year > 2035:
                errors.append(f"action_date {date_str} is out of plausible range")
        except ValueError:
            errors.append(f"action_date '{date_str}' is not in YYYY-MM-DD format")

    status = data.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"status '{status}' not in {VALID_STATUSES}")

    regulator = data.get("regulator")
    if regulator and regulator not in VALID_REGULATORS:
        logger.warning("Unknown regulator '%s' — flagging for review", regulator)

    return (data if not errors else None), errors


def validate_json_against_schema(raw: str, required_fields: list[str]) -> tuple[Optional[dict], list[str]]:
    errors: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"JSON parse error: {exc}"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    return (data if not errors else None), errors
