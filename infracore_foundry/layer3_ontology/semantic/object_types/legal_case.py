from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import IndianDate_Type


class LegalCase(OntologyObjectBase):
    caseId: str
    courtName: Optional[str] = None
    caseType: Optional[str] = None
    filingDate: Optional[IndianDate_Type] = None
    currentStatus: Optional[str] = None
    lastHearingDate: Optional[IndianDate_Type] = None
    caseSummary: Optional[str] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.caseId

    def compute_data_quality_score(self) -> float:
        critical = ["caseId", "courtName", "caseType", "currentStatus"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "legal_case"
        display_name = "Legal Case"
        plural_name = "Legal Cases"
        description = "A court case involving a company or director"
        primary_key_field = "caseId"
        critical_properties = ["caseId", "courtName", "caseType", "currentStatus"]


LEGAL_CASE_DEFINITION = {
    "api_name": "legal_case",
    "display_name": "Legal Case",
    "plural_name": "Legal Cases",
    "description": "A court case involving a company or director",
    "primary_key_field": "caseId",
    "datasource_mapping": {"legal_cases": "infracore/legal_cases.parquet"},
    "properties": [
        {"name": "caseId", "type": "str", "required": True, "immutable": True},
        {"name": "courtName", "type": "str"},
        {"name": "caseType", "type": "str"},
        {"name": "filingDate", "type": "IndianDate_Type"},
        {"name": "currentStatus", "type": "str"},
        {"name": "lastHearingDate", "type": "IndianDate_Type"},
        {"name": "caseSummary", "type": "str"},
    ],
    "interfaces": ["TemporalEntity"],
}
