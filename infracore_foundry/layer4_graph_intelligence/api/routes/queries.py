from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.middleware.auth import verify_api_key
from query_builder.query_executor import QueryExecutor
from query_builder.query_parser import QueryParser

router = APIRouter(prefix="/query", tags=["natural-language-query"])
_executor = QueryExecutor()
_parser = QueryParser()


class NLQueryRequest(BaseModel):
    query: str
    requested_by: str = "anonymous"


@router.post("/nl")
async def natural_language_query(
    req: NLQueryRequest,
    _key: str = Depends(verify_api_key),
):
    """Execute a natural-language graph query (claude-sonnet-4-6 powered)."""
    return await _executor.execute_natural_language(req.query, requested_by=req.requested_by)


@router.post("/parse")
async def parse_only(
    req: NLQueryRequest,
    _key: str = Depends(verify_api_key),
):
    """Parse a natural-language query without executing it."""
    parsed = await _parser.parse(req.query)
    return parsed.to_dict()
