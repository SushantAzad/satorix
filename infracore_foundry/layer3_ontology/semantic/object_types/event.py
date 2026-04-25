from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import IndianDate_Type


class Event(OntologyObjectBase):
    eventId: str
    date: Optional[IndianDate_Type] = None
    eventType: Optional[str] = None
    headline: Optional[str] = None
    source: Optional[str] = None
    sentiment: Optional[str] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.eventId

    def compute_data_quality_score(self) -> float:
        critical = ["eventId", "date", "headline", "eventType"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "event"
        display_name = "Event"
        plural_name = "Events"
        description = "A significant event related to a company or entity"
        primary_key_field = "eventId"
        critical_properties = ["eventId", "date", "headline", "eventType"]


EVENT_DEFINITION = {
    "api_name": "event",
    "display_name": "Event",
    "plural_name": "Events",
    "description": "A significant event related to a company or entity",
    "primary_key_field": "eventId",
    "properties": [
        {"name": "eventId", "type": "str", "required": True, "immutable": True},
        {"name": "date", "type": "IndianDate_Type"},
        {"name": "eventType", "type": "str"},
        {"name": "headline", "type": "str"},
        {"name": "source", "type": "str"},
        {"name": "sentiment", "type": "str"},
    ],
    "interfaces": ["TemporalEntity"],
}
