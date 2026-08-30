"""One authenticated, fixture-only mutation. General sync stays blocked."""
import logging
import secrets
from fastapi import APIRouter, Header, HTTPException
from shared.fixture_operation import authorize_fixture, require_local_storage

router = APIRouter(prefix="/fixtures", tags=["Local synthetic fixtures"])
logger = logging.getLogger(__name__)


@router.post("/import")
def import_fixture(body: dict, x_api_key: str = Header(default="")):
    # Validate before constructing a DB session. Never use the permissive no-key
    # fallback of the general API authentication helper for this exception.
    from layer1_ingestion.core.config import get_settings
    from layer1_ingestion.sync.fixture_import import ingest_fixture
    try:
        authorize_fixture(body)
        settings = get_settings()
        require_local_storage(settings)
        if not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(status_code=403, detail="Fixture API key required")
        return ingest_fixture(body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Local fixture import failed")
        raise HTTPException(status_code=503, detail="Local fixture storage/import failed") from exc
