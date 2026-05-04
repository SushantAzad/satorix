"""
Layer 6 authentication helpers — JWT creation, verification, password hashing, and
FastAPI dependency wrappers for role-based access control.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing — use bcrypt directly (passlib 1.7.4 is incompatible with bcrypt ≥4)
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches the stored bcrypt *hashed_password*."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning("verify_password error: %s", exc)
        return False


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash for *password*."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(data: Dict) -> str:
    """Encode *data* into a signed JWT that expires in settings.jwt_expire_minutes."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token


def _decode_token(token: str) -> Dict:
    """Decode and validate a JWT, raising HTTPException on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict:
    """Require a valid Bearer token and return the decoded payload as a dict."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Dict]:
    """Like get_current_user but returns None when no token is provided."""
    if credentials is None:
        return None
    try:
        return _decode_token(credentials.credentials)
    except HTTPException:
        return None


class RoleChecker:
    """
    FastAPI dependency that enforces role membership.

    Usage::

        Depends(RoleChecker(["analyst", "platform_administrator"]))
    """

    # All valid roles in the platform
    VALID_ROLES: List[str] = [
        "platform_administrator",
        "ontology_designer",
        "data_steward",
        "analyst",
        "compliance_head",
        "restricted_viewer",
        "system_pipeline",
    ]

    def __init__(self, allowed_roles: List[str]) -> None:
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        current_user: Dict = Depends(get_current_user),
    ) -> Dict:
        user_role: str = current_user.get("role", "")
        if user_role not in self.allowed_roles:
            logger.warning(
                "Access denied for user %s with role %s — required one of %s",
                current_user.get("sub"),
                user_role,
                self.allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' is not permitted to access this resource.",
            )
        return current_user
