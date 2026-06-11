"""
Session Router — routes incoming WebSocket messages from clients to the
appropriate ConnectionManager / aggregator actions.
"""
import logging
from typing import Dict

from core.layer_clients import layer_clients
from websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class SessionRouter:
    """
    Handles incoming JSON messages from a single WebSocket session.

    Supported message types:
    - subscribe        → subscribe to entity updates
    - unsubscribe      → remove entity subscription
    - ping             → respond with pong (keep-alive)
    - get_alerts       → push current unacknowledged alerts
    """

    def __init__(self, manager: ConnectionManager, session_id: str) -> None:
        self.manager = manager
        self.session_id = session_id

    async def handle(self, message: Dict) -> None:
        """Dispatch an incoming message to the correct handler."""
        msg_type: str = message.get("type", "")

        handlers = {
            "subscribe": self._handle_subscribe,
            "unsubscribe": self._handle_unsubscribe,
            "ping": self._handle_ping,
            "get_alerts": self._handle_get_alerts,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(message)
        else:
            logger.debug(
                "Unknown WS message type '%s' from session %s", msg_type, self.session_id
            )
            await self.manager.send_to_session(
                self.session_id,
                {"type": "error", "message": f"Unknown message type: {msg_type}"},
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_subscribe(self, message: Dict) -> None:
        entity_type: str = message.get("entity_type", "")
        entity_id: str = message.get("entity_id", "")
        if not entity_type or not entity_id:
            await self.manager.send_to_session(
                self.session_id,
                {"type": "error", "message": "subscribe requires entity_type and entity_id"},
            )
            return
        await self.manager.subscribe_to_entity(
            self.session_id, entity_type, entity_id
        )

    async def _handle_unsubscribe(self, message: Dict) -> None:
        entity_type: str = message.get("entity_type", "")
        entity_id: str = message.get("entity_id", "")
        if not entity_type or not entity_id:
            return
        await self.manager.unsubscribe_from_entity(
            self.session_id, entity_type, entity_id
        )
        await self.manager.send_to_session(
            self.session_id,
            {
                "type": "unsubscribed",
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

    async def _handle_ping(self, message: Dict) -> None:
        await self.manager.send_to_session(
            self.session_id, {"type": "pong"}
        )

    async def _handle_get_alerts(self, message: Dict) -> None:
        """Fetch current unacknowledged alerts and push to this session."""
        from aggregators.alerts import get_alert_list
        try:
            result = await get_alert_list(
                layer_clients, acknowledged=False, limit=20
            )
            await self.manager.send_to_session(
                self.session_id,
                {"type": "alerts", "data": result},
            )
        except Exception as exc:
            logger.warning("get_alerts WS handler failed: %s", exc)
            await self.manager.send_to_session(
                self.session_id,
                {"type": "error", "message": "Failed to fetch alerts"},
            )
