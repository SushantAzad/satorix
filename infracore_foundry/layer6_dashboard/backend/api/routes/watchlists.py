"""
Watchlist routes — per-user entity watchlists stored in l6_watchlists.
"""
import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from core.auth import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AddWatchlistRequest(BaseModel):
    entity_type: str
    entity_id: str
    entity_name: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/")
async def get_watchlist(
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict]:
    """Return the current user's watchlist."""
    result = await db.execute(
        text(
            """
            SELECT id, entity_type, entity_id, entity_name, added_at, notes
            FROM l6_watchlists
            WHERE user_id = :user_id
            ORDER BY added_at DESC
            """
        ),
        {"user_id": current_user["sub"]},
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r.id),
            "entityType": r.entity_type,
            "entityId": r.entity_id,
            "entityName": r.entity_name,
            "addedAt": r.added_at.isoformat() if r.added_at else None,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: AddWatchlistRequest,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Add an entity to the user's watchlist."""
    # Check for duplicate
    check = await db.execute(
        text(
            """
            SELECT id FROM l6_watchlists
            WHERE user_id = :user_id
              AND entity_type = :entity_type
              AND entity_id = :entity_id
            """
        ),
        {
            "user_id": current_user["sub"],
            "entity_type": body.entity_type,
            "entity_id": body.entity_id,
        },
    )
    existing = check.fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity is already in watchlist.",
        )

    entry_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO l6_watchlists (id, user_id, entity_type, entity_id, entity_name, added_at, notes)
            VALUES (:id, :user_id, :entity_type, :entity_id, :entity_name, NOW(), :notes)
            """
        ),
        {
            "id": entry_id,
            "user_id": current_user["sub"],
            "entity_type": body.entity_type,
            "entity_id": body.entity_id,
            "entity_name": body.entity_name,
            "notes": body.notes,
        },
    )
    await db.commit()
    return {
        "id": entry_id,
        "entityType": body.entity_type,
        "entityId": body.entity_id,
        "entityName": body.entity_name,
        "notes": body.notes,
        "message": "Added to watchlist.",
    }


@router.delete("/{entity_type}/{entity_id}", status_code=status.HTTP_200_OK)
async def remove_from_watchlist(
    entity_type: str,
    entity_id: str,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Remove an entity from the user's watchlist."""
    result = await db.execute(
        text(
            """
            DELETE FROM l6_watchlists
            WHERE user_id = :user_id
              AND entity_type = :entity_type
              AND entity_id = :entity_id
            """
        ),
        {
            "user_id": current_user["sub"],
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found in watchlist.",
        )
    return {"message": "Removed from watchlist.", "entityType": entity_type, "entityId": entity_id}


@router.get("/check/{entity_type}/{entity_id}")
async def check_watchlist(
    entity_type: str,
    entity_id: str,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Check if an entity is in the current user's watchlist."""
    result = await db.execute(
        text(
            """
            SELECT id, notes, added_at
            FROM l6_watchlists
            WHERE user_id = :user_id
              AND entity_type = :entity_type
              AND entity_id = :entity_id
            """
        ),
        {
            "user_id": current_user["sub"],
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )
    row = result.fetchone()
    if row:
        return {
            "inWatchlist": True,
            "id": str(row.id),
            "notes": row.notes,
            "addedAt": row.added_at.isoformat() if row.added_at else None,
        }
    return {"inWatchlist": False}
