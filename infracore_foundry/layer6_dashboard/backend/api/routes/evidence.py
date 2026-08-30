"""Authenticated source-record inspection for the local synthetic fixture only."""
from fastapi import APIRouter, Depends, HTTPException, Response
from core.auth import get_current_user
from shared.fixture_evidence import read_fixture_evidence

router = APIRouter()


@router.get("/fixtures/{record_id}")
def get_fixture_evidence(record_id: str, response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return read_fixture_evidence(record_id, user.get("client_id", ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Fixture evidence is not authorized or failed integrity validation") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Fixture record not found") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Fixture evidence is unavailable") from exc
