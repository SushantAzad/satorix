from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class OntologyObjectBase(BaseModel):
    """Base class for all ontology object types."""
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    riskScore: Optional[int] = None
    riskFlags: list[str] = []
    dataQualityScore: Optional[float] = None
    lastUpdated: Optional[datetime] = None
    notes: Optional[str] = None

    def primary_key_value(self) -> str:
        raise NotImplementedError

    def compute_data_quality_score(self) -> float:
        """Compute completeness score for critical properties."""
        raise NotImplementedError

    class OntologyMeta:
        api_name: str = ""
        display_name: str = ""
        plural_name: str = ""
        description: str = ""
        primary_key_field: str = ""
        datasource_mapping: dict = {}
        critical_properties: list[str] = []
