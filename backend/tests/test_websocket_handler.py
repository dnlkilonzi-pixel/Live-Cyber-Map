"""Unit tests for the WebSocket endpoint handler.

Tests cover: _handle_command (all branches including invalid JSON),
_send_initial_history (with/without processor, exception path),
and _redis_forwarder (cancelled path, message forwarding, non-message filtering).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.websocket.handler as handler_module
from app.websocket.handler import (
    _handle_command,
    _redis_forwarder,
    _send_initial_history,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


def _sent_json(ws: AsyncMock, call_index: int = 0) -> dict:
    """Decode the JSON string passed to ws.send_text at *call_index*."""
    raw = ws.send_text.call_args_list[call_index][0][0]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# _handle_command – valid commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_pause():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "pause"}))
    msg = _sent_json(ws)
    assert msg == {"type": "ack", "command": "pause"}


@pytest.mark.asyncio
async def test_handle_resume():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "resume"}))
    msg = _sent_json(ws)
    assert msg == {"type": "ack", "command": "resume"}


@pytest.mark.asyncio
async def test_handle_set_speed_default():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "set_speed"}))
    msg = _sent_json(ws)
    assert msg["type"] == "ack"
    assert msg["command"] == "set_speed"
    assert msg["speed"] == 1.0


@pytest.mark.asyncio
async def test_handle_set_speed_custom():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "set_speed", "speed": 2.5}))
    msg = _sent_json(ws)
    assert msg["speed"] == 2.5


@pytest.mark.asyncio
async def test_handle_replay():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "replay"}))
    msg = _sent_json(ws)
    assert msg["type"] == "ack"
    assert msg["command"] == "replay"
    assert msg["status"] == "not_implemented"


@pytest.mark.asyncio
async def test_handle_ping():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "ping"}))
    msg = _sent_json(ws)
    assert msg == {"type": "pong"}


@pytest.mark.asyncio
async def test_handle_stats():
    ws = _make_ws()
    with patch("app.websocket.handler.anomaly_detector") as mock_ad:
        mock_ad.get_stats.return_value = {"events_per_sec": 3.5}
        await _handle_command(ws, json.dumps({"command": "stats"}))
    msg = _sent_json(ws)
    assert msg["type"] == "stats"
    assert "data" in msg


@pytest.mark.asyncio
async def test_handle_unknown_command():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "fly_to_moon"}))
    msg = _sent_json(ws)
    assert msg["type"] == "error"
    assert "fly_to_moon" in msg["detail"]


@pytest.mark.asyncio
async def test_handle_empty_command():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({}))
    msg = _sent_json(ws)
    # empty string command → "Unknown command: " error
    assert msg["type"] == "error"


# ---------------------------------------------------------------------------
# _handle_command – invalid JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_invalid_json():
    ws = _make_ws()
    await _handle_command(ws, "this is not json")
    msg = _sent_json(ws)
    assert msg["type"] == "error"
    assert "Invalid JSON" in msg["detail"]


# ---------------------------------------------------------------------------
# _send_initial_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_initial_history_with_processor():
    ws = _make_ws()
    mock_processor = MagicMock()
    mock_processor.get_recent_events.return_value = [{"id": "1"}]

    with (
        patch.object(handler_module, "__builtins__", __builtins__),
        patch("app.websocket.handler.anomaly_detector") as mock_ad,
        patch("app.websocket.handler.ws_manager") as mock_mgr,
    ):
        mock_ad.get_stats.return_value = {"events": 0}
        mock_mgr.get_connection_count.return_value = 1

        # Patch the lazy import inside the function
        with patch.dict("sys.modules", {}):
            import sys

            # Inject a fake app.main module with our mock processor
            fake_main = MagicMock()
            fake_main.processor = mock_processor
            old_main = sys.modules.get("app.main")
            sys.modules["app.main"] = fake_main
            try:
                await _send_initial_history(ws)
            finally:
                if old_main is not None:
                    sys.modules["app.main"] = old_main
                else:
                    del sys.modules["app.main"]

    msg = _sent_json(ws)
    assert msg["type"] == "init"
    assert isinstance(msg["events"], list)
    assert "stats" in msg
    assert "connection_count" in msg


@pytest.mark.asyncio
async def test_send_initial_history_no_processor():
    ws = _make_ws()
    with patch("app.websocket.handler.anomaly_detector") as mock_ad:
        mock_ad.get_stats.return_value = {}
        with patch("app.websocket.handler.ws_manager") as mock_mgr:
            mock_mgr.get_connection_count.return_value = 0
            import sys

            fake_main = MagicMock()
            fake_main.processor = None
            old_main = sys.modules.get("app.main")
            sys.modules["app.main"] = fake_main
            try:
                await _send_initial_history(ws)
            finally:
                if old_main is not None:
                    sys.modules["app.main"] = old_main
                else:
                    del sys.modules["app.main"]

    msg = _sent_json(ws)
    assert msg["type"] == "init"
    assert msg["events"] == []


@pytest.mark.asyncio
async def test_send_initial_history_exception_is_swallowed():
    """Even if everything explodes, _send_initial_history must not propagate."""
    ws = _make_ws()
    ws.send_text.side_effect = Exception("socket closed")
    with patch("app.websocket.handler.anomaly_detector") as mock_ad:
        mock_ad.get_stats.return_value = {}
        with patch("app.websocket.handler.ws_manager") as mock_mgr:
            mock_mgr.get_connection_count.return_value = 0
            import sys

            fake_main = MagicMock()
            fake_main.processor = None
            old_main = sys.modules.get("app.main")
            sys.modules["app.main"] = fake_main
            try:
                await _send_initial_history(ws)  # should not raise
            finally:
                if old_main is not None:
                    sys.modules["app.main"] = old_main
                else:
                    del sys.modules["app.main"]


# ---------------------------------------------------------------------------
# _redis_forwarder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_forwarder_cancelled():
    """CancelledError is absorbed silently."""
    ws = _make_ws()
    mock_redis = MagicMock()
    pubsub = AsyncMock()

    async def never_yield():
        raise asyncio.CancelledError()
        yield  # make it an async generator

    pubsub.listen = never_yield
    pubsub.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = pubsub

    await _redis_forwarder(ws, mock_redis)  # should not raise


@pytest.mark.asyncio
async def test_redis_forwarder_skips_non_message_type():
    ws = _make_ws()
    mock_redis = MagicMock()
    pubsub = AsyncMock()

    async def fake_listen():
        yield {"type": "subscribe", "data": 1}
        raise asyncio.CancelledError()

    pubsub.listen = fake_listen
    pubsub.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = pubsub

    await _redis_forwarder(ws, mock_redis)
    ws.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_forwarder_forwards_attack_message():
    ws = _make_ws()
    mock_redis = MagicMock()
    pubsub = AsyncMock()

    attack_data = {"source_country": "CN", "attack_type": "DDoS"}

    async def fake_listen():
        yield {"type": "message", "data": json.dumps(attack_data)}
        raise asyncio.CancelledError()

    pubsub.listen = fake_listen
    pubsub.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = pubsub

    with patch("app.websocket.handler.anomaly_detector") as mock_ad:
        mock_ad.add_event = MagicMock()
        await _redis_forwarder(ws, mock_redis)

    ws.send_text.assert_awaited_once()
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["type"] == "attack"
    assert sent["data"] == attack_data
    mock_ad.add_event.assert_called_once_with(attack_data)


@pytest.mark.asyncio
async def test_redis_forwarder_handles_bad_json_gracefully():
    ws = _make_ws()
    mock_redis = MagicMock()
    pubsub = AsyncMock()

    async def fake_listen():
        yield {"type": "message", "data": "not-json!!!"}
        raise asyncio.CancelledError()

    pubsub.listen = fake_listen
    pubsub.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = pubsub

    await _redis_forwarder(ws, mock_redis)  # should not raise
    ws.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_forwarder_handles_outer_exception():
    ws = _make_ws()
    mock_redis = MagicMock()
    mock_redis.pubsub.side_effect = RuntimeError("redis gone")

    await _redis_forwarder(ws, mock_redis)  # should not propagate
