"""
Auth routes — login, /me, logout, and default admin bootstrap.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from core.auth import (
    RoleChecker,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from core.config import get_settings
from core.database import L6User, async_session_maker, get_db

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict


# ---------------------------------------------------------------------------
# Default admin bootstrapping
# ---------------------------------------------------------------------------

async def ensure_default_admin() -> None:
    """
    If the l6_users table is empty, create the default platform administrator.
    Called once during application startup.
    """
    async with async_session_maker() as db:
        try:
            result = await db.execute(text("SELECT COUNT(*) FROM l6_users"))
            count = result.scalar()
            if count and count > 0:
                await db.execute(
                    text("UPDATE l6_users SET client_id = :client_id WHERE email = :email"),
                    {"client_id": settings.default_admin_client_id, "email": settings.default_admin_email},
                )
                await db.commit()
                return

            logger.info("Creating default admin user: %s", settings.default_admin_email)
            await db.execute(
                text(
                    """
                    INSERT INTO l6_users (id, email, name, password_hash, role, client_id, is_active, created_at)
                    VALUES (:id, :email, :name, :password_hash, :role, :client_id, TRUE, NOW())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "email": settings.default_admin_email,
                    "name": "Platform Administrator",
                    "password_hash": get_password_hash(settings.default_admin_password),
                    "role": "platform_administrator",
                    "client_id": settings.default_admin_client_id,
                },
            )
            await db.commit()
            logger.info("Default admin user created.")
        except Exception as exc:
            logger.warning("ensure_default_admin failed: %s", exc)
            await db.rollback()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> Dict:
    """Authenticate a user and return a JWT access token."""
    result = await db.execute(
        text("SELECT * FROM l6_users WHERE email = :email AND is_active = TRUE"),
        {"email": body.email.lower().strip()},
    )
    user_row = result.fetchone()

    if user_row is None or not verify_password(body.password, user_row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Update last_login
    try:
        await db.execute(
            text("UPDATE l6_users SET last_login = NOW() WHERE id = :id"),
            {"id": str(user_row.id)},
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to update last_login: %s", exc)

    token_data = {
        "sub": str(user_row.id),
        "email": user_row.email,
        "role": user_row.role,
        "client_id": user_row.client_id,
        "name": user_row.name,
    }
    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user_row.id),
            "email": user_row.email,
            "name": user_row.name,
            "role": user_row.role,
            "client_id": user_row.client_id,
        },
    }


@router.get("/me")
async def get_me(
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Return the authenticated user's profile."""
    result = await db.execute(
        text("SELECT * FROM l6_users WHERE id = :id"),
        {"id": current_user["sub"]},
    )
    user_row = result.fetchone()
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return {
        "id": str(user_row.id),
        "email": user_row.email,
        "name": user_row.name,
        "role": user_row.role,
        "client_id": user_row.client_id,
        "is_active": user_row.is_active,
        "created_at": user_row.created_at.isoformat() if user_row.created_at else None,
        "last_login": user_row.last_login.isoformat() if user_row.last_login else None,
    }


@router.post("/logout")
async def logout(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Client-side logout — invalidation happens by discarding the token.
    For MVP there is no server-side token revocation.
    """
    return {"message": "Logged out successfully."}
