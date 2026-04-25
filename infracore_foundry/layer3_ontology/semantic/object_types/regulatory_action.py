from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import IndianDate_Type


class RegulatoryAction(OntologyObjectBase):
    actionId: str
    issuingBody: Optional[str] = None
    actionType: Optional[str] = None
    actionDate: IndianDate_Type
    resolutionDate: Optional[IndianDate_Type] = None
    monetaryAmount: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.actionId

    def compute_data_quality_score(self) -> float:
        critical = ["actionId", "issuingBody", "actionType", "actionDate", "status"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "regulatory_action"
        display_name = "Regulatory Action"
        plural_name = "Regulatory Actions"
        description = "A regulatory action issued by a body against a company or director"
        primary_key_field = "actionId"
        critical_properties = ["actionId", "issuingBody", "actionType", "actionDate", "status"]


REGULATORY_ACTION_DEFINITION = {
    "api_name": "regulatory_action",
    "display_name": "Regulatory Action",
    "plural_name": "Regulatory Actions",
    "description": "A regulatory action issued by a body against a company or director",
    "primary_key_field": "actionId",
    "datasource_mapping": {"regulatory_actions": "infracore/regulatory_actions.parquet"},
    "properties": [
        {"name": "actionId", "type": "str", "required": True, "immutable": True},
        {"name": "issuingBody", "type": "str"},
        {"name": "actionType", "type": "str"},
        {"name": "actionDate", "type": "IndianDate_Type", "required": True},
        {"name": "resolutionDate", "type": "IndianDate_Type"},
        {"name": "monetaryAmount", "type": "Currency_INR"},
        {"name": "status", "type": "str"},
        {"name": "description", "type": "str"},
    ],
    "interfaces": ["TemporalEntity"],
}
