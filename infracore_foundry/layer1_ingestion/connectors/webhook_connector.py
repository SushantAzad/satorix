"""
Webhook receiver for push-based data ingestion.
Does NOT inherit BaseConnector — fundamentally different architecture.
Handles registration, HMAC verification, payload processing.
"""

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from layer1_ingestion.core.storage import upload_parquet, generate_object_path

logger = logging.getLogger(__name__)


@dataclass
class WebhookEndpoint:
    """Registered webhook endpoint configuration."""
    source_id: str
    token: str
    secret_key: str
    payload_schema: Optional[dict] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


@dataclass
class ProcessingResult:
    """Result of processing a webhook payload."""
    success: bool
    source_id: str
    records_processed: int
    output_path: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WebhookDelivery:
    """Log entry for a webhook delivery attempt."""
    id: str
    source_id: str
    received_at: datetime
    payload_size: int
    status: str  # received, verified, processed, failed
    processing_result: Optional[ProcessingResult] = None
    error: Optional[str] = None


class WebhookReceiver:
    """
    Webhook receiver for push-based data ingestion.
    Handles endpoint registration, HMAC signature verification,
    payload validation, and data conversion to Parquet.
    """

    def __init__(self) -> None:
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._delivery_log: list[WebhookDelivery] = []

    def register_webhook(
        self,
        source_id: str,
        secret_key: str,
        payload_schema: Optional[dict] = None,
    ) -> WebhookEndpoint:
        """
        Register a new webhook endpoint.
        Creates a unique token for the endpoint URL: /webhooks/{source_id}/{token}
        """
        token = uuid.uuid4().hex
        endpoint = WebhookEndpoint(
            source_id=source_id,
            token=token,
            secret_key=secret_key,
            payload_schema=payload_schema,
        )
        self._endpoints[source_id] = endpoint
        logger.info(
            "Registered webhook endpoint",
            extra={"source_id": source_id, "endpoint_url": f"/webhooks/{source_id}/{token}"},
        )
        return endpoint

    def get_endpoint(self, source_id: str) -> Optional[WebhookEndpoint]:
        """Retrieve a registered webhook endpoint."""
        return self._endpoints.get(source_id)

    def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """
        Verify HMAC-SHA256 signature of a webhook payload.
        The signature should be in format: sha256=<hex_digest>
        """
        if not signature or not secret:
            return False

        expected_sig = signature
        if expected_sig.startswith("sha256="):
            expected_sig = expected_sig[7:]

        computed = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed, expected_sig)

    def validate_payload(self, payload: dict, schema: Optional[dict]) -> list[str]:
        """Validate payload against the registered schema."""
        errors = []
        if schema is None:
            return errors

        required_fields = schema.get("required_fields", [])
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(f"Missing required field: {field_name}")

        expected_types = schema.get("field_types", {})
        for field_name, expected_type in expected_types.items():
            if field_name in payload:
                value = payload[field_name]
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field_name}' expected string, got {type(value).__name__}")
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{field_name}' expected number, got {type(value).__name__}")
                elif expected_type == "array" and not isinstance(value, list):
                    errors.append(f"Field '{field_name}' expected array, got {type(value).__name__}")

        return errors

    def process_payload(
        self,
        source_id: str,
        payload: dict,
        client_id: str = "webhook",
    ) -> ProcessingResult:
        """
        Process a webhook payload: validate, convert to DataFrame, upload to MinIO.
        """
        endpoint = self._endpoints.get(source_id)
        delivery = WebhookDelivery(
            id=uuid.uuid4().hex,
            source_id=source_id,
            received_at=datetime.now(timezone.utc),
            payload_size=len(json.dumps(payload)),
            status="received",
        )

        try:
            # Validate against schema
            if endpoint and endpoint.payload_schema:
                validation_errors = self.validate_payload(payload, endpoint.payload_schema)
                if validation_errors:
                    delivery.status = "failed"
                    delivery.error = "; ".join(validation_errors)
                    self._delivery_log.append(delivery)
                    return ProcessingResult(
                        success=False, source_id=source_id,
                        records_processed=0, errors=validation_errors,
                    )

            delivery.status = "verified"

            # Convert payload to DataFrame
            if "data" in payload and isinstance(payload["data"], list):
                records = payload["data"]
            elif "records" in payload and isinstance(payload["records"], list):
                records = payload["records"]
            elif isinstance(payload, list):
                records = payload
            else:
                records = [payload]

            df = pd.json_normalize(records)

            if df.empty:
                delivery.status = "processed"
                self._delivery_log.append(delivery)
                return ProcessingResult(
                    success=True, source_id=source_id,
                    records_processed=0,
                )

            # Upload to MinIO as Parquet
            object_path = generate_object_path(client_id, source_id)
            output_path = upload_parquet(df, "raw-data", object_path)

            delivery.status = "processed"
            result = ProcessingResult(
                success=True,
                source_id=source_id,
                records_processed=len(df),
                output_path=output_path,
            )
            delivery.processing_result = result
            self._delivery_log.append(delivery)

            logger.info(
                "Webhook payload processed",
                extra={
                    "source_id": source_id,
                    "records": len(df),
                    "output_path": output_path,
                },
            )
            return result

        except Exception as e:
            delivery.status = "failed"
            delivery.error = str(e)
            self._delivery_log.append(delivery)
            logger.error(
                "Webhook processing failed: %s", str(e),
                extra={"source_id": source_id},
            )
            return ProcessingResult(
                success=False, source_id=source_id,
                records_processed=0, errors=[str(e)],
            )

    def get_delivery_logs(self, source_id: str, limit: int = 50) -> list[WebhookDelivery]:
        """Get recent webhook delivery logs for a source."""
        logs = [d for d in self._delivery_log if d.source_id == source_id]
        return sorted(logs, key=lambda d: d.received_at, reverse=True)[:limit]

    def deactivate_endpoint(self, source_id: str) -> bool:
        """Deactivate a webhook endpoint."""
        endpoint = self._endpoints.get(source_id)
        if endpoint:
            endpoint.is_active = False
            return True
        return False


# Global webhook receiver instance
webhook_receiver = WebhookReceiver()
