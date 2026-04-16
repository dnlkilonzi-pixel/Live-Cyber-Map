"""WebSocket connection manager.

Manages all active WebSocket connections and provides broadcast helpers.
Also runs a background Redis subscriber that forwards published attack
events to every connected client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_REDIS_CHANNEL = "attacks"
_MAX_CONNECTIONS_PER_IP = 5
# Rate-limit: max new WS connections per IP per time window
_WS_RATE_WINDOW = 60.0   # seconds
_WS_RATE_MAX = 20        # new connections allowed per window per IP


class WebSocketManager:
    """Singleton that tracks live WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._active: Set[WebSocket] = set()
        self._redis = None        # injected at startup
        self._sub_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        # Channel → set of WebSockets (for future targeted broadcasts)
        self._channels: Dict[str, Set[WebSocket]] = {}
        # Per-IP connection count for connection-count limiting
        self._ip_counts: Dict[str, int] = defaultdict(int)
        # Per-IP connection timestamps for rate-limiting (sliding window)
        self._ip_connect_times: Dict[str, List[float]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept and register a new WebSocket connection.

        Returns False and rejects the connection if:
        - the client IP already has *_MAX_CONNECTIONS_PER_IP* or more active connections, OR
        - the client IP has made *_WS_RATE_MAX* or more new connections in the last
          *_WS_RATE_WINDOW* seconds (connection rate-limit).
        """
        client_ip = self._get_ip(websocket)

        # --- Connection-count limit ---
        if self._ip_counts[client_ip] >= _MAX_CONNECTIONS_PER_IP:
            logger.warning(
                "WS connection refused for %s — already at %d connections",
                client_ip, _MAX_CONNECTIONS_PER_IP,
            )
            await websocket.accept()
            await websocket.close(code=1008, reason="Too many connections from this IP")
            return False

        # --- Connection rate-limit (sliding window) ---
        now = time.time()
        window_start = now - _WS_RATE_WINDOW
        self._ip_connect_times[client_ip] = [
            t for t in self._ip_connect_times[client_ip] if t > window_start
        ]
        if len(self._ip_connect_times[client_ip]) >= _WS_RATE_MAX:
            logger.warning(
                "WS connection rate-limit hit for %s — %d attempts in %.0fs",
                client_ip, len(self._ip_connect_times[client_ip]), _WS_RATE_WINDOW,
            )
            await websocket.accept()
            await websocket.close(code=1008, reason="Connection rate limit exceeded")
            return False
        self._ip_connect_times[client_ip].append(now)

        await websocket.accept()
        self._active.add(websocket)
        self._ip_counts[client_ip] += 1
        logger.info(
            "WS connected [%s] — total: %d (IP connections: %d)",
            client_ip, len(self._active), self._ip_counts[client_ip],
        )
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        self._active.discard(websocket)
        # Clean up any channel memberships
        for members in self._channels.values():
            members.discard(websocket)
        client_ip = self._get_ip(websocket)
        if self._ip_counts[client_ip] > 0:
            self._ip_counts[client_ip] -= 1
        # Prune stale rate-limit state once no active connections remain
        if self._ip_counts[client_ip] == 0:
            self._prune_stale_ip_state(client_ip)
        logger.info("WS disconnected — total: %d", len(self._active))

    def _prune_stale_ip_state(self, ip: str) -> None:
        """Remove rate-limit history for *ip* if all timestamps are outside the window.

        Called after the last connection from an IP is closed so that the
        ``_ip_connect_times`` and ``_ip_counts`` dicts don't grow unboundedly.
        """
        now = time.time()
        window_start = now - _WS_RATE_WINDOW
        recent = [t for t in self._ip_connect_times.get(ip, []) if t > window_start]
        if recent:
            # Keep only the trimmed list; IP may reconnect soon
            self._ip_connect_times[ip] = recent
        else:
            # No activity in the window → evict entirely
            self._ip_connect_times.pop(ip, None)
            self._ip_counts.pop(ip, None)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, message: Dict, priority: int = 0) -> None:
        """Send *message* (as JSON) to every connected client.

        Low-priority messages (priority < 0) are skipped when the active
        connection set is large enough to create back-pressure concerns.
        """
        if not self._active:
            return
        # Back-pressure: drop low-priority events when >50 clients connected
        if priority < 0 and len(self._active) > 50:
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_ip(websocket: WebSocket) -> str:
        """Extract the client IP from the WebSocket connection."""
        try:
            # Prefer the X-Forwarded-For header (behind a proxy)
            forwarded = websocket.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
            if websocket.client:
                return websocket.client.host
        except Exception:
            pass
        return "unknown"


# Module-level singleton
ws_manager = WebSocketManager()
