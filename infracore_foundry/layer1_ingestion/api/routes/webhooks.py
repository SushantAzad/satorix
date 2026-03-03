"""Webhook receiver routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from layer1_ingestion.core.database import get_db
from layer1_ingestion.connectors.webhook_connector import webhook_receiver
from layer1_ingestion.api.schemas.models import (
    WebhookRegisterRequest, WebhookRegisterResponse, WebhookPayloadResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/register", response_model=WebhookRegisterResponse)
def register_webhook(body: WebhookRegisterRequest, db: Session = Depends(get_db)):
    endpoint = webhook_receiver.register_webhook(
        source_id=body.source_id,
        secret_key=body.secret_key,
        payload_schema=body.payload_schema,
    )
    return WebhookRegisterResponse(
        source_id=endpoint.source_id,
        token=endpoint.token,
        endpoint_url=f"/webhooks/{endpoint.source_id}/{endpoint.token}",
    )


@router.post("/{source_id}/{token}", response_model=WebhookPayloadResponse)
async def receive_webhook(
    source_id: str,
    token: str,
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
):
    endpoint = webhook_receiver.get_endpoint(source_id)
    if endpoint is None or endpoint.token != token:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    if not endpoint.is_active:
        raise HTTPException(status_code=410, detail="Webhook endpoint is deactivated")

    body = await request.body()
    if x_hub_signature_256:
        if not webhook_receiver.verify_signature(body, x_hub_signature_256, endpoint.secret_key):
            raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    result = webhook_receiver.process_payload(source_id, payload)
    return WebhookPayloadResponse(
        success=result.success,
        records_processed=result.records_processed,
        output_path=result.output_path,
        errors=result.errors,
    )
