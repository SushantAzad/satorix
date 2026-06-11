"""Shared property definitions used across multiple object types."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from .indian_types import RiskScore_Type


class SharedProperties(BaseModel):
    """Mixin for properties shared across object types."""
    riskScore: Optional[RiskScore_Type] = None
    status: Optional[str] = None
    registeredState: Optional[str] = None
    lastUpdated: Optional[datetime] = None
    dataQualityScore: Optional[float] = None

    @field_validator("dataQualityScore")
    @classmethod
    def validate_quality_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("dataQualityScore must be 0–100")
        return v

    @field_validator("registeredState")
    @classmethod
    def normalize_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from .indian_types import normalize_state
        return normalize_state(v)
