"""
Intelligence dashboard routes — surfaces Layer 5 predictions, features,
correlations, and the open-ended reasoning agent to the frontend.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from core.auth import get_current_user
from aggregators.intelligence import get_intelligence_dashboard, ask_intelligence_question

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    cin: Optional[str] = None


@router.get("/{cin}")
async def get_company_intelligence(
    cin: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get full intelligence dashboard data for a company.
    Includes CIRP prediction, risk features, trends, benchmarks,
    correlations, scenarios, and network influence.
    """
    data = await get_intelligence_dashboard(cin)
    if not data:
        raise HTTPException(status_code=404, detail=f"No intelligence data found for {cin}")
    return data


@router.post("/ask")
async def ask_question(
    request: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Ask an open-ended corporate intelligence question.
    The GraphIntelligenceAgent answers using multi-step tool-use reasoning
    grounded in the knowledge graph and indexed documents.
    """
    if not request.question or len(request.question.strip()) < 5:
        raise HTTPException(status_code=422, detail="Question must be at least 5 characters")
    return await ask_intelligence_question(request.question, request.cin)
