"""Authentication boundary for privileged Ontology operations.

The Ontology must never accept an Action from an anonymous client.  Until the
platform's OIDC service is introduced, service-to-service callers use the
platform API key and forward a trusted actor identity from the BFF.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from core.config import settings


async def require_platform_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Fail closed when the platform key is absent or does not match."""
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ontology action API is not configured with API_KEY.",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid platform API key.",
        )
