"""
Structured extraction workflow (Type 2) — LLM reads unstructured documents and
produces structured data written back to the ontology via the L3 Object Data Funnel.
"""
import json
import logging

import httpx

from core.config import settings
from llm.orchestrator import llm_orchestrator
from llm.output_validator import validate_regulatory_action

logger = logging.getLogger(__name__)


async def extract_regulatory_action(
    document_text: str,
    actor_id: str = "system",
    actor_role: str = "system",
    write_to_ontology: bool = True,
) -> dict:
    """
    Extract regulatory action details from a SEBI/RBI/ED order PDF text.
    Validates output and optionally writes to L3 via Object Data Funnel.
    Returns {extracted_data, validation_errors, written_to_ontology}.
    """
    raw = await llm_orchestrator.run(
        prompt_key="regulatory_extraction_v1",
        format_kwargs={"document_text": document_text[:4000]},
        actor_id=actor_id,
        actor_role=actor_role,
        output_disposition="stored",
        max_tokens=512,
        workflow_type="structured_extraction",
        use_cache=False,
    )

    validated, errors = validate_regulatory_action(raw)

    written = False
    if validated and not errors and write_to_ontology:
        written = await _write_regulatory_action_to_l3(validated, actor_id)

    return {
        "extracted_data": validated,
        "raw_llm_output": raw,
        "validation_errors": errors,
        "written_to_ontology": written,
    }


async def _write_regulatory_action_to_l3(data: dict, actor_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.layer3_api_url}/api/v1/ingest/objects",
                json={
                    "object_type": "regulatory_action",
                    "properties": data,
                    "source": "l5_llm_extraction",
                    "actor_id": actor_id,
                },
            )
            if resp.status_code in (200, 201):
                logger.info("Regulatory action written to L3 ontology: %s", data.get("entity_name"))
                return True
            logger.warning("L3 write failed: %s %s", resp.status_code, resp.text[:200])
            return False
    except Exception as exc:
        logger.error("L3 write error: %s", exc)
        return False
