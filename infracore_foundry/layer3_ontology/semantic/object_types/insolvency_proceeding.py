from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import IndianDate_Type


class InsolvencyProceeding(OntologyObjectBase):
    cirpId: str
    admissionDate: Optional[IndianDate_Type] = None
    resolutionProfessional: Optional[str] = None
    totalAdmittedClaims: Optional[float] = None
    status: Optional[str] = None
    resolutionApplicant: Optional[str] = None
    haircutPercent: Optional[float] = None
    lastUpdated: Optional[datetime] = None

    def primary_key_value(self) -> str:
        return self.cirpId

    def compute_data_quality_score(self) -> float:
        critical = ["cirpId", "admissionDate", "status"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "insolvency_proceeding"
        display_name = "Insolvency Proceeding"
        plural_name = "Insolvency Proceedings"
        description = "A CIRP or insolvency proceeding under IBC"
        primary_key_field = "cirpId"
        critical_properties = ["cirpId", "admissionDate", "status"]


INSOLVENCY_PROCEEDING_DEFINITION = {
    "api_name": "insolvency_proceeding",
    "display_name": "Insolvency Proceeding",
    "plural_name": "Insolvency Proceedings",
    "description": "A CIRP or insolvency proceeding under IBC",
    "primary_key_field": "cirpId",
    "datasource_mapping": {"insolvency": "infracore/insolvency.parquet"},
    "properties": [
        {"name": "cirpId", "type": "str", "required": True, "immutable": True},
        {"name": "admissionDate", "type": "IndianDate_Type"},
        {"name": "resolutionProfessional", "type": "str"},
        {"name": "totalAdmittedClaims", "type": "Currency_INR"},
        {"name": "status", "type": "str"},
        {"name": "resolutionApplicant", "type": "str"},
        {"name": "haircutPercent", "type": "float"},
    ],
    "interfaces": ["TemporalEntity"],
}
