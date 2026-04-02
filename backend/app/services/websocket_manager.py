"""WebSocket connection manager.

Manages all active WebSocket connections and provides broadcast helpers.
Also runs a background Redis subscriber that forwards published attack
events to every connected client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_REDIS_CHANNEL = "attacks"


class WebSocketManager:
    """Singleton that tracks live WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._active: Set[WebSocket] = set()
        self._redis = None        # injected at startup
        self._sub_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        # Channel → set of WebSockets (for future targeted broadcasts)
        self._channels: Dict[str, Set[WebSocket]] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._active.add(websocket)
        logger.info("WS connected — total: %d", len(self._active))

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        self._active.discard(websocket)
        # Clean up any channel memberships
        for members in self._channels.values():
            members.discard(websocket)
        logger.info("WS disconnected — total: %d", len(self._active))

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, message: Dict) -> None:
        """Send *message* (as JSON) to every connected client."""
        if not self._active:
            return
        payload = json.dumps(message, default=str)
        dead: Set[WebSocket] = set()
        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        # Prune disconnected sockets
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_to_channel(self, channel: str, message: Dict) -> None:
        """Send *message* only to clients subscribed to *channel*."""
        members = self._channels.get(channel, set())
        if not members:
            return
        payload = json.dumps(message, default=str)
        dead: Set[WebSocket] = set()
        for ws in list(members):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    def subscribe_to_channel(self, channel: str, websocket: WebSocket) -> None:
        """Add *websocket* to a named channel."""
        self._channels.setdefault(channel, set()).add(websocket)

    def unsubscribe_from_channel(self, channel: str, websocket: WebSocket) -> None:
        """Remove *websocket* from a named channel."""
        self._channels.get(channel, set()).discard(websocket)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_connection_count(self) -> int:
        """Return the number of currently connected clients."""
        return len(self._active)

    # ------------------------------------------------------------------
    # Redis subscriber
    # ------------------------------------------------------------------

    def set_redis(self, redis_client) -> None:
        """Inject the Redis client and start the subscriber task."""
        self._redis = redis_client

    async def start_redis_subscriber(self) -> None:
        """Start the background task that forwards Redis messages to WS clients."""
        if self._redis is None:
            logger.warning("Redis not available — WS broadcast will use direct path only.")
            return
        self._sub_task = asyncio.create_task(self._redis_listener())
        logger.info("WebSocketManager Redis subscriber started.")

    async def stop_redis_subscriber(self) -> None:
        """Cancel the Redis subscriber task."""
        if self._sub_task:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass

    async def _redis_listener(self) -> None:
        """Subscribe to the 'attacks' channel and broadcast every message."""
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(_REDIS_CHANNEL)
            logger.info("Subscribed to Redis channel '%s'.", _REDIS_CHANNEL)

            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                    await self.broadcast({"type": "attack", "data": data})
                except (json.JSONDecodeError, Exception) as exc:
                    logger.debug("Failed to process Redis message: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Redis subscriber error: %s", exc)


# Module-level singleton
ws_manager = WebSocketManager()
