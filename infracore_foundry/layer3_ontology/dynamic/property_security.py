from .roles import Role

SENSITIVE_PROPERTIES: dict[str, dict[str, str]] = {
    "company": {
        "internalInvestigationNotes": "platform_administrator",
        "personalMobileNumber": "compliance_head",
    },
    "director": {
        "personalAddress": "compliance_head",
        "disqualificationDetails": "compliance_head",
    },
}

_ROLE_LEVELS: dict[str, int] = {
    "restricted_viewer": 0,
    "analyst": 1,
    "operations_team": 2,
    "compliance_head": 3,
    "data_steward": 4,
    "ontology_designer": 5,
    "platform_administrator": 6,
    "system_pipeline": 4,
    "system": 6,
}

REDACTED_VALUE = "[REDACTED — insufficient permissions]"


class PropertySecurityMiddleware:
    def apply_masking(
        self,
        object_type: str,
        properties: dict,
        actor_role: str,
    ) -> dict:
        sensitive = SENSITIVE_PROPERTIES.get(object_type.lower(), {})
        if not sensitive:
            return properties

        actor_level = _ROLE_LEVELS.get(actor_role.lower(), 0)
        result = dict(properties)

        for field, min_role in sensitive.items():
            min_level = _ROLE_LEVELS.get(min_role.lower(), 6)
            if actor_level < min_level and field in result:
                result[field] = REDACTED_VALUE

        return result

    def can_read_property(self, object_type: str, property_name: str, actor_role: str) -> bool:
        sensitive = SENSITIVE_PROPERTIES.get(object_type.lower(), {})
        if property_name not in sensitive:
            return True
        min_role = sensitive[property_name]
        actor_level = _ROLE_LEVELS.get(actor_role.lower(), 0)
        min_level = _ROLE_LEVELS.get(min_role.lower(), 6)
        return actor_level >= min_level


property_security = PropertySecurityMiddleware()
