from typing import Optional
from datetime import datetime
from pydantic import field_validator
from .base import OntologyObjectBase
from semantic.properties.indian_types import DIN_Type


class Director(OntologyObjectBase):
    din: DIN_Type
    name: str
    nationality: Optional[str] = None
    city: Optional[str] = None
    disqualificationStatus: Optional[str] = None
    currentDirectorships: Optional[int] = None
    historicalDirectorships: Optional[int] = None
    isOffshore: Optional[bool] = None
    notes: Optional[str] = None

    # Derived
    riskScore: Optional[int] = None
    riskFlags: list[str] = []
    dataQualityScore: Optional[float] = None
    lastUpdated: Optional[datetime] = None
    boardConcentrationScore: Optional[float] = None
    regulatoryExposureScore: Optional[float] = None

    @field_validator("isOffshore", mode="before")
    @classmethod
    def compute_offshore(cls, v: Optional[bool], info: any) -> Optional[bool]:
        if v is not None:
            return v
        values = info.data if hasattr(info, "data") else {}
        nationality = values.get("nationality", "")
        if nationality:
            return nationality.upper() not in ("INDIAN", "INDIA", "IN")
        return None

    @field_validator("disqualificationStatus")
    @classmethod
    def validate_disq(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "None"
        allowed = {"None", "Disqualified"}
        for a in allowed:
            if a.lower() == v.lower():
                return a
        return v

    def primary_key_value(self) -> str:
        return str(self.din)

    def compute_data_quality_score(self) -> float:
        critical = ["din", "name", "nationality", "disqualificationStatus"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "director"
        display_name = "Director"
        plural_name = "Directors"
        description = "An individual serving as director in one or more Indian companies"
        primary_key_field = "din"
        critical_properties = ["din", "name", "nationality", "disqualificationStatus"]


DIRECTOR_DEFINITION = {
    "api_name": "director",
    "display_name": "Director",
    "plural_name": "Directors",
    "description": "An individual serving as director in one or more Indian companies",
    "primary_key_field": "din",
    "datasource_mapping": {"director_master": "infracore/directors.parquet"},
    "properties": [
        {"name": "din", "type": "DIN_Type", "required": True, "immutable": True},
        {"name": "name", "type": "str", "required": True},
        {"name": "nationality", "type": "str"},
        {"name": "city", "type": "str"},
        {"name": "disqualificationStatus", "type": "str"},
        {"name": "currentDirectorships", "type": "int"},
        {"name": "historicalDirectorships", "type": "int"},
        {"name": "isOffshore", "type": "bool", "derived": True},
        {"name": "notes", "type": "str", "user_editable": True},
        {"name": "riskScore", "type": "RiskScore_Type", "derived": True},
        {"name": "riskFlags", "type": "list[str]", "derived": True},
        {"name": "boardConcentrationScore", "type": "float", "derived": True},
        {"name": "regulatoryExposureScore", "type": "float", "derived": True},
    ],
    "interfaces": ["RegulatableEntity", "TemporalEntity"],
}
