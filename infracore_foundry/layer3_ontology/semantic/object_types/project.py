from typing import Optional
from datetime import datetime
from .base import OntologyObjectBase
from semantic.properties.indian_types import IndianDate_Type, normalize_state


class Project(OntologyObjectBase):
    projectId: str
    name: str
    projectType: Optional[str] = None
    state: Optional[str] = None
    contractedBy: Optional[str] = None
    contractDate: Optional[IndianDate_Type] = None
    expectedCompletionDate: Optional[IndianDate_Type] = None
    actualCompletionDate: Optional[IndianDate_Type] = None
    status: Optional[str] = None
    totalCost: Optional[float] = None
    debtComponent: Optional[float] = None
    equityComponent: Optional[float] = None
    concessionYears: Optional[int] = None
    revenueModel: Optional[str] = None
    currentAnnualRevenue: Optional[float] = None
    delayMonths: Optional[int] = None
    costOverrunPercent: Optional[float] = None
    environmentalClearance: Optional[str] = None
    landAcquisitionStatus: Optional[str] = None
    keyRisk: Optional[str] = None

    # Derived
    riskScore: Optional[int] = None
    riskFlags: list[str] = []
    dataQualityScore: Optional[float] = None
    lastUpdated: Optional[datetime] = None
    notes: Optional[str] = None
    delayRatio: Optional[float] = None
    costOverrunRatio: Optional[float] = None
    debtServiceCoverageRatio: Optional[float] = None

    def primary_key_value(self) -> str:
        return self.projectId

    def compute_data_quality_score(self) -> float:
        critical = ["projectId", "name", "status", "totalCost"]
        present = sum(1 for f in critical if getattr(self, f, None) is not None)
        return round((present / len(critical)) * 100, 2)

    class OntologyMeta:
        api_name = "project"
        display_name = "Project"
        plural_name = "Projects"
        description = "An infrastructure project owned by one or more companies"
        primary_key_field = "projectId"
        critical_properties = ["projectId", "name", "status", "totalCost", "ownerCIN"]


PROJECT_DEFINITION = {
    "api_name": "project",
    "display_name": "Project",
    "plural_name": "Projects",
    "description": "An infrastructure project",
    "primary_key_field": "projectId",
    "datasource_mapping": {"projects": "infracore/projects.parquet"},
    "properties": [
        {"name": "projectId", "type": "str", "required": True, "immutable": True},
        {"name": "name", "type": "str", "required": True},
        {"name": "projectType", "type": "str"},
        {"name": "state", "type": "str"},
        {"name": "contractedBy", "type": "str"},
        {"name": "status", "type": "str"},
        {"name": "totalCost", "type": "Currency_INR"},
        {"name": "debtComponent", "type": "Currency_INR"},
        {"name": "equityComponent", "type": "Currency_INR"},
        {"name": "riskScore", "type": "RiskScore_Type", "derived": True},
    ],
    "interfaces": ["FinancialEntity", "GeographicEntity", "TemporalEntity"],
}
