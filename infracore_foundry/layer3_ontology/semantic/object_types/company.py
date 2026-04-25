from pydantic import field_validator, model_validator
from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import CIN_Type, Currency_INR, IndianDate_Type, RiskScore_Type, normalize_state


class Company(OntologyObjectBase):
    # Immutable primary key
    cin: CIN_Type

    # Core properties
    name: str
    incorporationDate: Optional[IndianDate_Type] = None
    registeredState: Optional[str] = None
    companyType: Optional[str] = None
    industry: Optional[str] = None
    authorizedCapital: Optional[float] = None
    paidUpCapital: Optional[float] = None
    status: Optional[str] = None
    listedStatus: Optional[str] = None
    registeredAddress: Optional[str] = None
    pin: Optional[str] = None

    # Derived (computed by intelligence layer)
    riskScore: Optional[int] = None
    riskFlags: list[str] = []
    dataQualityScore: Optional[float] = None
    lastUpdated: Optional[datetime] = None
    notes: Optional[str] = None

    # Derived — computed at query time from graph
    subsidiaryCount: Optional[int] = None
    directorCount: Optional[int] = None
    regulatoryActionCount: Optional[int] = None
    offshoreExposureFlag: Optional[bool] = None
    groupRiskScore: Optional[float] = None

    @field_validator("registeredState")
    @classmethod
    def normalize_state_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_state(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"Active", "StrikeOff", "UnderCIRP", "Dormant", "Archived", None}
        if v not in allowed:
            # Don't raise — normalize case
            for a in allowed:
                if a and a.lower() == (v or "").lower():
                    return a
        return v

    @field_validator("companyType")
    @classmethod
    def validate_company_type(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"Public Limited", "Private Limited", "LLP", "OPC", None}
        return v

    def primary_key_value(self) -> str:
        return str(self.cin)

    def compute_data_quality_score(self) -> float:
        critical = ["cin", "name", "status", "registeredState", "riskScore"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "company"
        display_name = "Company"
        plural_name = "Companies"
        description = "An Indian registered company entity"
        primary_key_field = "cin"
        datasource_mapping = {
            "company_master": "infracore/company_master.parquet",
        }
        critical_properties = ["cin", "name", "status", "registeredState", "riskScore"]


COMPANY_DEFINITION = {
    "api_name": "company",
    "display_name": "Company",
    "plural_name": "Companies",
    "description": "An Indian registered company entity",
    "primary_key_field": "cin",
    "datasource_mapping": {"company_master": "infracore/company_master.parquet"},
    "properties": [
        {"name": "cin", "type": "CIN_Type", "required": True, "immutable": True},
        {"name": "name", "type": "str", "required": True},
        {"name": "incorporationDate", "type": "IndianDate_Type"},
        {"name": "registeredState", "type": "str"},
        {"name": "companyType", "type": "str"},
        {"name": "industry", "type": "str"},
        {"name": "authorizedCapital", "type": "Currency_INR"},
        {"name": "paidUpCapital", "type": "Currency_INR"},
        {"name": "status", "type": "str"},
        {"name": "listedStatus", "type": "str"},
        {"name": "registeredAddress", "type": "str"},
        {"name": "pin", "type": "str"},
        {"name": "riskScore", "type": "RiskScore_Type", "derived": True},
        {"name": "riskFlags", "type": "list[str]", "derived": True},
        {"name": "dataQualityScore", "type": "float", "derived": True},
        {"name": "lastUpdated", "type": "datetime"},
        {"name": "notes", "type": "str", "user_editable": True},
    ],
    "interfaces": ["RegulatableEntity", "FinancialEntity", "GeographicEntity", "TemporalEntity"],
}
