"""
WebSocket Connection Manager — tracks connected sessions, per-user sessions,
and per-entity subscribers; routes messages to the right clients.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Central registry and message dispatcher for all active WebSocket connections.

    Lifecycle::

        await manager.connect(ws, session_id, user_id)
        # ... exchange messages ...
        await manager.disconnect(session_id)
    """

    def __init__(self) -> None:
        # session_id → WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # user_id → session_id (most-recent session wins)
        self.user_sessions: Dict[str, str] = {}
        # entity_key ("company:L452…") → set of session_ids
        self.entity_subscribers: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(
        self, websocket: WebSocket, session_id: str, user_id: str
    ) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.user_sessions[user_id] = session_id
        logger.info(
            "WebSocket connected: session=%s user=%s total=%d",
            session_id,
            user_id,
            len(self.active_connections),
        )
        # Send welcome message
        await self.send_to_session(
            session_id,
            {
                "type": "connected",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def disconnect(self, session_id: str) -> None:
        """Remove a session and clean up all subscriptions."""
        self.active_connections.pop(session_id, None)

        # Remove from user_sessions
        for uid, sid in list(self.user_sessions.items()):
            if sid == session_id:
                del self.user_sessions[uid]
                break

        # Remove from entity subscriptions
        for key in list(self.entity_subscribers.keys()):
            self.entity_subscribers[key].discard(session_id)
            if not self.entity_subscribers[key]:
                del self.entity_subscribers[key]

        logger.info(
            "WebSocket disconnected: session=%s total=%d",
            session_id,
            len(self.active_connections),
        )

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def subscribe_to_entity(
        self, session_id: str, entity_type: str, entity_id: str
    ) -> None:
        """Subscribe a session to updates for a specific entity."""
        key = f"{entity_type}:{entity_id}"
        self.entity_subscribers.setdefault(key, set()).add(session_id)
        logger.debug("Session %s subscribed to entity %s", session_id, key)
        await self.send_to_session(
            session_id,
            {
                "type": "subscribed",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def unsubscribe_from_entity(
        self, session_id: str, entity_type: str, entity_id: str
    ) -> None:
        """Unsubscribe a session from entity updates."""
        key = f"{entity_type}:{entity_id}"
        if key in self.entity_subscribers:
            self.entity_subscribers[key].discard(session_id)
            if not self.entity_subscribers[key]:
                del self.entity_subscribers[key]
        logger.debug("Session %s unsubscribed from entity %s", session_id, key)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_to_session(self, session_id: str, message: Dict) -> None:
        """Send a JSON message to a specific session (silently skip if gone)."""
        ws = self.active_connections.get(session_id)
        if ws is None:
            return
        try:
            await ws.send_json(message)
        except Exception as exc:
            logger.warning(
                "Failed to send message to session %s: %s — disconnecting.",
                session_id,
                exc,
            )
            await self.disconnect(session_id)

    async def broadcast_entity_update(
        self, entity_type: str, entity_id: str, data: Dict
    ) -> None:
        """Broadcast an entity update to all sessions subscribed to that entity."""
        key = f"{entity_type}:{entity_id}"
        subscribers = list(self.entity_subscribers.get(key, set()))
        if not subscribers:
            return

        message = {
            "type": "entity_update",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug(
            "Broadcasting entity_update for %s to %d session(s).", key, len(subscribers)
        )
        for session_id in subscribers:
            await self.send_to_session(session_id, message)

    async def broadcast_alert(self, alert: Dict) -> None:
        """Broadcast a new alert to ALL connected sessions."""
        if not self.active_connections:
            return

        message = {
            "type": "new_alert",
            "data": alert,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug(
            "Broadcasting new_alert to %d session(s).", len(self.active_connections)
        )
        for session_id in list(self.active_connections.keys()):
            await self.send_to_session(session_id, message)

    async def send_system_notification(
        self, message: str, level: str = "info"
    ) -> None:
        """Send a system-level notification to all connected sessions."""
        payload = {
            "type": "system_notification",
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for session_id in list(self.active_connections.keys()):
            await self.send_to_session(session_id, payload)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connected_count(self) -> int:
        return len(self.active_connections)


# Module-level singleton
manager = ConnectionManager()
