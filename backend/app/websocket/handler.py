"""WebSocket endpoint handler.

Handles the /ws WebSocket connection lifecycle:
- Sends recent event history on connect
- Processes client commands (pause, resume, set_speed, replay)
- Subscribes to Redis and forwards new attack events in real time
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.anomaly_detector import anomaly_detector
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_REDIS_CHANNEL = "attacks"
# How many events to replay to a freshly connected client
_INITIAL_HISTORY_COUNT = 50


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for the Live Cyber Map."""
    accepted = await ws_manager.connect(websocket)
    sub_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # connect() returns False when the IP limit is exceeded (already closed)
    if not accepted:
        return

    try:
        # ------------------------------------------------------------------ #
        # 1. Send initial burst of recent events so the map is not blank
        # ------------------------------------------------------------------ #
        await _send_initial_history(websocket)

        # ------------------------------------------------------------------ #
        # 2. If Redis is unavailable, fall back to direct-broadcast mode.
        #    Otherwise launch a dedicated per-connection Redis subscriber so
        #    this client still gets events even if the global subscriber lags.
        # ------------------------------------------------------------------ #
        from app.main import redis_client  # noqa: PLC0415

        if redis_client is not None:
            sub_task = asyncio.create_task(_redis_forwarder(websocket, redis_client))

        # ------------------------------------------------------------------ #
        # 3. Command loop — handle messages from the client
        # ------------------------------------------------------------------ #
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                await _handle_command(websocket, raw)
            except asyncio.TimeoutError:
                # Send a heartbeat ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        ws_manager.disconnect(websocket)
        if sub_task:
            sub_task.cancel()
            try:
                await sub_task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _send_initial_history(websocket: WebSocket) -> None:
    """Push recent events and current stats to a newly connected client."""
    try:
        from app.main import processor  # noqa: PLC0415

        events = (
            processor.get_recent_events(_INITIAL_HISTORY_COUNT) if processor else []
        )
        stats = anomaly_detector.get_stats()

        await websocket.send_text(
            json.dumps(
                {
                    "type": "init",
                    "events": events,
                    "stats": stats,
                    "connection_count": ws_manager.get_connection_count(),
                },
                default=str,
            )
        )
    except Exception as exc:
        logger.warning("Failed to send initial history: %s", exc)


async def _redis_forwarder(websocket: WebSocket, redis_client) -> None:
    """Subscribe to the Redis 'attacks' channel and forward to this client."""
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(_REDIS_CHANNEL)

        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            try:
                data = json.loads(raw["data"])
                # Feed into anomaly detector as well
                anomaly_detector.add_event(data)
                payload = json.dumps({"type": "attack", "data": data}, default=str)
                await websocket.send_text(payload)
            except Exception as exc:
                logger.debug("Error forwarding Redis message to WS: %s", exc)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("Redis forwarder stopped: %s", exc)


async def _handle_command(websocket: WebSocket, raw: str) -> None:
    """Parse and execute a JSON command sent by the client."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_text(
            json.dumps({"type": "error", "detail": "Invalid JSON"})
        )
        return

    command = msg.get("command", "")

    if command == "pause":
        await websocket.send_text(json.dumps({"type": "ack", "command": "pause"}))

    elif command == "resume":
        await websocket.send_text(json.dumps({"type": "ack", "command": "resume"}))

    elif command == "set_speed":
        speed = msg.get("speed", 1.0)
        await websocket.send_text(
            json.dumps({"type": "ack", "command": "set_speed", "speed": speed})
        )

    elif command == "replay":
        await websocket.send_text(
            json.dumps(
                {"type": "ack", "command": "replay", "status": "not_implemented"}
            )
        )

    elif command == "stats":
        stats = anomaly_detector.get_stats()
        await websocket.send_text(json.dumps({"type": "stats", "data": stats}))

    elif command == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))

    else:
        await websocket.send_text(
            json.dumps({"type": "error", "detail": f"Unknown command: {command}"})
        )
