"""
WebSocket route — handles client connections, authentication, and message routing.
"""
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from core.config import get_settings
from websocket.manager import manager
from websocket.session_router import SessionRouter

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


def _authenticate_ws_token(token: Optional[str]) -> Optional[dict]:
    """Decode and validate a JWT token for WebSocket authentication."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        logger.warning("WebSocket JWT decode failed: %s", exc)
        return None


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint at /ws/{session_id}.

    Authentication: pass token as query param: /ws/my-session?token=<jwt>

    Supported message types once connected:
    - {"type": "subscribe", "entity_type": "company", "entity_id": "L45201MH..."}
    - {"type": "unsubscribe", "entity_type": "company", "entity_id": "..."}
    - {"type": "ping"}
    - {"type": "get_alerts"}
    """
    # Authenticate via query param token
    token: Optional[str] = websocket.query_params.get("token")
    user_payload = _authenticate_ws_token(token)

    if user_payload is None:
        logger.warning(
            "WebSocket connection rejected (no/invalid token) for session %s", session_id
        )
        await websocket.close(code=4001, reason="Authentication required")
        return

    user_id: str = user_payload.get("sub", session_id)

    # Connect
    await manager.connect(websocket, session_id, user_id)
    session_router = SessionRouter(manager, session_id)

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                await manager.send_to_session(
                    session_id,
                    {"type": "error", "message": "Expected a JSON object"},
                )
                continue
            await session_router.handle(data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally: session=%s user=%s", session_id, user_id)
    except Exception as exc:
        logger.warning("WebSocket error for session %s: %s", session_id, exc)
    finally:
        await manager.disconnect(session_id)
