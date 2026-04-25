from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase


class GovernmentEntity(OntologyObjectBase):
    entityId: str
    name: str
    ministry: Optional[str] = None
    department: Optional[str] = None
    level: Optional[str] = None
    state: Optional[str] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.entityId

    def compute_data_quality_score(self) -> float:
        critical = ["entityId", "name", "level"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "government_entity"
        display_name = "Government Entity"
        plural_name = "Government Entities"
        description = "A government ministry, department, or authority"
        primary_key_field = "entityId"
        critical_properties = ["entityId", "name", "level"]


GOVERNMENT_ENTITY_DEFINITION = {
    "api_name": "government_entity",
    "display_name": "Government Entity",
    "plural_name": "Government Entities",
    "description": "A government ministry, department, or authority",
    "primary_key_field": "entityId",
    "properties": [
        {"name": "entityId", "type": "str", "required": True, "immutable": True},
        {"name": "name", "type": "str", "required": True},
        {"name": "ministry", "type": "str"},
        {"name": "department", "type": "str"},
        {"name": "level", "type": "str"},
        {"name": "state", "type": "str"},
    ],
    "interfaces": ["TemporalEntity"],
}
