from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase


class RegulatoryBody(OntologyObjectBase):
    bodyId: str
    name: str
    jurisdiction: Optional[str] = None
    sector: Optional[str] = None
    governingLegislation: Optional[str] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.bodyId

    def compute_data_quality_score(self) -> float:
        critical = ["bodyId", "name", "jurisdiction"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "regulatory_body"
        display_name = "Regulatory Body"
        plural_name = "Regulatory Bodies"
        description = "A government regulatory authority"
        primary_key_field = "bodyId"
        critical_properties = ["bodyId", "name", "jurisdiction"]


REGULATORY_BODY_DEFINITION = {
    "api_name": "regulatory_body",
    "display_name": "Regulatory Body",
    "plural_name": "Regulatory Bodies",
    "description": "A government regulatory authority",
    "primary_key_field": "bodyId",
    "properties": [
        {"name": "bodyId", "type": "str", "required": True, "immutable": True},
        {"name": "name", "type": "str", "required": True},
        {"name": "jurisdiction", "type": "str"},
        {"name": "sector", "type": "str"},
        {"name": "governingLegislation", "type": "str"},
    ],
    "interfaces": ["TemporalEntity"],
}
