"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Data Source Schemas ---
class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(..., description="csv, excel, postgresql, rest_api, mca21, etc.")
    client_id: str = Field(..., min_length=1, max_length=100)
    config: dict = Field(default_factory=dict)
    credentials: Optional[dict] = None
    description: Optional[str] = None
    sync_schedule: Optional[str] = None
    tags: Optional[list[str]] = None


class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    credentials: Optional[dict] = None
    description: Optional[str] = None
    sync_schedule: Optional[str] = None
    tags: Optional[list[str]] = None
    is_active: Optional[bool] = None


class DataSourceResponse(BaseModel):
    id: UUID
    name: str
    source_type: str
    client_id: str
    config: dict
    description: Optional[str]
    is_active: bool
    sync_schedule: Optional[str]
    tags: Optional[list[str]]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DataSourceListResponse(BaseModel):
    total: int
    items: list[DataSourceResponse]


# --- Sync Schemas ---
class SyncTriggerRequest(BaseModel):
    sync_type: str = Field(default="incremental", description="full or incremental")


class SyncRunResponse(BaseModel):
    id: UUID
    source_id: UUID
    sync_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    records_extracted: Optional[int]
    output_path: Optional[str]
    error_details: Optional[str]

    class Config:
        from_attributes = True


# --- Health Schemas ---
class HealthCheckResponse(BaseModel):
    source_id: UUID
    status: str
    response_time_ms: float
    error_message: Optional[str]
    checked_at: datetime

    class Config:
        from_attributes = True


# --- Alert Schemas ---
class AlertResponse(BaseModel):
    id: UUID
    source_id: UUID
    alert_type: str
    severity: str
    message: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


# --- Profile Schemas ---
class ProfileRequest(BaseModel):
    source_id: UUID


class ColumnProfileResponse(BaseModel):
    column_name: str
    detected_type: str
    indian_identifier_type: Optional[str]
    completeness_score: float
    uniqueness_score: float
    pattern_conformance: Optional[float]
    anomaly_flags: list[str]


class ProfileReportResponse(BaseModel):
    source_id: str
    profiled_at: datetime
    total_records: int
    total_columns: int
    overall_quality_score: float
    columns: list[ColumnProfileResponse]
    cross_field_issues: list[dict]
    recommendations: list[str]


# --- Connection Test ---
class ConnectionTestRequest(BaseModel):
    source_type: str
    config: dict
    credentials: Optional[dict] = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    response_time_ms: float
    error: Optional[str] = None


# --- Webhook Schemas ---
class WebhookRegisterRequest(BaseModel):
    source_id: str
    secret_key: str
    payload_schema: Optional[dict] = None


class WebhookRegisterResponse(BaseModel):
    source_id: str
    token: str
    endpoint_url: str


class WebhookPayloadResponse(BaseModel):
    success: bool
    records_processed: int
    output_path: Optional[str]
    errors: list[str]
