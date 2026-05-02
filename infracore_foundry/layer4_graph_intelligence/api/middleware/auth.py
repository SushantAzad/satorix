import logging
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from core.config import settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    if not settings.api_key:
        logger.warning("API_KEY not configured — all requests accepted (dev mode)")
        return "dev"
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
