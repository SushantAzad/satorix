"""API key authentication dependency for FastAPI routes."""

import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from layer1_ingestion.core.config import get_settings

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Optional[str] = Security(_API_KEY_HEADER)) -> str:
    """
    FastAPI dependency — validates the X-API-Key header.

    Returns the validated key on success.
    Raises HTTP 401 on missing key, HTTP 403 on invalid key.

    If API_KEY is not configured in settings (empty string), authentication
    is disabled and a warning is logged — for local development only.
    """
    settings = get_settings()

    if not settings.api_key:
        # Dev mode: no key configured — allow all requests but warn loudly.
        import logging
        logging.getLogger(__name__).warning(
            "API_KEY is not set — authentication is DISABLED. "
            "Set API_KEY in .env before exposing this service."
        )
        return "dev-mode-no-auth"

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )

    # Constant-time comparison prevents timing-based key enumeration.
    if not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key
