"""LLM workflow endpoints."""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from llm.workflows.narrative import generate_path_narrative
from llm.workflows.extraction import extract_regulatory_action
from llm.workflows.summarization import summarize_company, explain_cirp_risk, generate_entity_intelligence
from llm.workflows.qa import answer_question

router = APIRouter(prefix="/llm", tags=["llm"])


class NarrativeRequest(BaseModel):
    source_id: str
    target_id: str
    node_path: list[str]
    node_types: list[str]
    hop_details: list[dict]
    signals: list[str] = []
    node_properties: dict[str, dict] = {}


class ExtractionRequest(BaseModel):
    document_text: str
    write_to_ontology: bool = False


class SummarizationRequest(BaseModel):
    cin: str
    cirp_probability: float = 0.0
    risk_score: int = 0
    risk_flags: list[str] = []


class QARequest(BaseModel):
    question: str
    context_cin: Optional[str] = None
    additional_context: Optional[dict] = None


class EntityIntelligenceRequest(BaseModel):
    entity_type: str
    entity_id: str
    context: dict = {}


@router.post("/narrative")
async def generate_narrative(
    request: NarrativeRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    text = await generate_path_narrative(
        source_id=request.source_id,
        target_id=request.target_id,
        node_path=request.node_path,
        node_types=request.node_types,
        hop_details=request.hop_details,
        signals=request.signals,
        node_properties=request.node_properties,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
    )
    return {"narrative": text}


@router.post("/extract/regulatory-action")
async def extract_regulatory(
    request: ExtractionRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    return await extract_regulatory_action(
        document_text=request.document_text,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
        write_to_ontology=request.write_to_ontology,
    )


@router.post("/summarize")
async def summarize(
    request: SummarizationRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    summary = await summarize_company(
        cin=request.cin,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
        cirp_probability=request.cirp_probability,
        risk_score=request.risk_score,
        risk_flags=request.risk_flags,
    )
    return {"summary": summary}


@router.post("/qa")
async def qa(
    request: QARequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    answer = await answer_question(
        question=request.question,
        context_cin=request.context_cin,
        additional_context=request.additional_context,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
    )
    return {"answer": answer}


@router.post("/entity-intelligence")
async def entity_intelligence(
    request: EntityIntelligenceRequest,
    x_actor_id: Optional[str] = Header(default="api_user"),
    x_actor_role: Optional[str] = Header(default="Analyst"),
):
    narrative = await generate_entity_intelligence(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        context=request.context,
        actor_id=x_actor_id or "api_user",
        actor_role=x_actor_role or "Analyst",
    )
    return {"narrative": narrative}
