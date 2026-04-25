from typing import Any
import logging

logger = logging.getLogger(__name__)

REQUIRED_FIELDS: dict[str, list[str]] = {
    "company": ["cin", "name"],
    "director": ["din", "name"],
    "project": ["projectId", "name"],
    "regulatory_action": ["actionId", "actionDate"],
    "legal_case": ["caseId"],
    "insolvency_proceeding": ["cirpId"],
    "address": ["normalizedAddress"],
    "regulatory_body": ["bodyId", "name"],
    "government_entity": ["entityId", "name"],
    "event": ["eventId"],
    "alert": ["alertId", "severity", "alertType", "title", "message"],
}


class SchemaValidator:
    def validate(self, object_type: str, data: dict[str, Any]) -> list[str]:
        """Returns list of validation errors. Empty list = valid."""
        errors: list[str] = []
        required = REQUIRED_FIELDS.get(object_type.lower(), [])

        for field in required:
            value = data.get(field)
            if value is None or str(value).strip() == "":
                errors.append(f"Required field missing: {field}")

        return errors

    def validate_batch(
        self, object_type: str, records: list[dict[str, Any]]
    ) -> tuple[list[dict], list[dict]]:
        """Returns (valid_records, rejected_records_with_errors)."""
        valid = []
        rejected = []
        for record in records:
            errors = self.validate(object_type, record)
            if errors:
                rejected.append({**record, "_validation_errors": errors})
            else:
                valid.append(record)
        return valid, rejected


schema_validator = SchemaValidator()
