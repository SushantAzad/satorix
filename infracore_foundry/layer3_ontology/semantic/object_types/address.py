from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase


class Address(OntologyObjectBase):
    normalizedAddress: str
    fullAddress: Optional[str] = None
    pin: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    companyCount: Optional[int] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.normalizedAddress

    def compute_data_quality_score(self) -> float:
        critical = ["normalizedAddress", "city", "state", "pin"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "address"
        display_name = "Address"
        plural_name = "Addresses"
        description = "A physical address — shared addresses are a key intelligence signal"
        primary_key_field = "normalizedAddress"
        critical_properties = ["normalizedAddress", "city", "state", "pin"]


ADDRESS_DEFINITION = {
    "api_name": "address",
    "display_name": "Address",
    "plural_name": "Addresses",
    "description": "A physical address — shared addresses are a key intelligence signal",
    "primary_key_field": "normalizedAddress",
    "datasource_mapping": {},
    "properties": [
        {"name": "normalizedAddress", "type": "str", "required": True, "immutable": True},
        {"name": "fullAddress", "type": "str"},
        {"name": "pin", "type": "str"},
        {"name": "city", "type": "str"},
        {"name": "state", "type": "str"},
        {"name": "companyCount", "type": "int", "derived": True},
    ],
    "interfaces": ["GeographicEntity", "TemporalEntity"],
}
