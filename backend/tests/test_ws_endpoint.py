"""Integration tests for the WebSocket endpoint (app/websocket/handler.py lines 33–83).

Tests cover: connection rejected, connection accepted + disconnect,
timeout → heartbeat ping → disconnect, Redis sub_task creation,
unhandled exception in the body, finally cleanup on sub_task,
and timeout → ping send failure → break.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from app.websocket.handler import _handle_command, websocket_endpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(return_value=None)
    ws.client = MagicMock()
    ws.client.host = "127.0.0.1"
    return ws


# ---------------------------------------------------------------------------
# Connection rejected (ws_manager.connect returns False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_rejected():
    """When connect() returns False the handler returns immediately without sending anything."""
    ws = _make_ws()
    with patch(
        "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=False)
    ):
        await websocket_endpoint(ws)
    ws.send_text.assert_not_called()


# ---------------------------------------------------------------------------
# Connection accepted → WebSocketDisconnect immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_accepted_normal_disconnect():
    """Accepted connection that disconnects immediately exits cleanly."""
    ws = _make_ws()
    ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    with (
        patch(
            "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=True)
        ),
        patch("app.websocket.handler._send_initial_history", new=AsyncMock()),
        patch("app.websocket.handler.ws_manager.disconnect") as mock_disconnect,
        patch("app.main.redis_client", None),
    ):
        await websocket_endpoint(ws)

    mock_disconnect.assert_called_once_with(ws)


# ---------------------------------------------------------------------------
# Connection accepted → unhandled exception → cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_generic_exception_cleaned_up():
    """Any unhandled exception exits the loop and calls disconnect in finally."""
    ws = _make_ws()
    ws.receive_text = AsyncMock(side_effect=RuntimeError("unexpected"))

    with (
        patch(
            "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=True)
        ),
        patch("app.websocket.handler._send_initial_history", new=AsyncMock()),
        patch("app.websocket.handler.ws_manager.disconnect") as mock_disconnect,
        patch("app.main.redis_client", None),
    ):
        await websocket_endpoint(ws)

    mock_disconnect.assert_called_once_with(ws)


# ---------------------------------------------------------------------------
# Connection accepted → timeout → ping succeeds → then disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_timeout_then_disconnect():
    """Heartbeat ping is sent on receive_text timeout; next timeout exits."""
    ws = _make_ws()
    ws.send_text = AsyncMock()

    call_count = 0

    async def receive_text_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncio.TimeoutError()
        # Second call: actual disconnect
        raise WebSocketDisconnect()

    ws.receive_text = receive_text_side_effect

    with (
        patch(
            "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=True)
        ),
        patch("app.websocket.handler._send_initial_history", new=AsyncMock()),
        patch("app.websocket.handler.ws_manager.disconnect"),
        patch("app.main.redis_client", None),
    ):
        await websocket_endpoint(ws)

    # The ping should have been sent
    ping_calls = [
        call
        for call in ws.send_text.call_args_list
        if json.loads(call.args[0]).get("type") == "ping"
    ]
    assert len(ping_calls) >= 1


# ---------------------------------------------------------------------------
# Connection accepted → timeout → ping send fails → break
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_timeout_ping_fails_breaks():
    """When heartbeat ping send raises, the loop breaks and disconnect is called."""
    ws = _make_ws()
    ping_call_count = 0

    async def send_text_mock(text):
        nonlocal ping_call_count
        data = json.loads(text)
        if data.get("type") == "ping":
            ping_call_count += 1
            raise RuntimeError("send failed")

    ws.send_text = send_text_mock
    ws.receive_text = AsyncMock(side_effect=asyncio.TimeoutError())

    with (
        patch(
            "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=True)
        ),
        patch("app.websocket.handler._send_initial_history", new=AsyncMock()),
        patch("app.websocket.handler.ws_manager.disconnect") as mock_disconnect,
        patch("app.main.redis_client", None),
    ):
        await websocket_endpoint(ws)

    assert ping_call_count >= 1
    mock_disconnect.assert_called_once_with(ws)


# ---------------------------------------------------------------------------
# Connection accepted with Redis → sub_task created and cancelled on disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_endpoint_with_redis_creates_sub_task():
    """With a non-None redis_client a sub_task is created and cancelled on disconnect."""
    ws = _make_ws()
    ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    mock_redis = AsyncMock()

    async def fake_redis_forwarder(websocket, redis_client):
        # Simulate hanging forever until cancelled
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            pass

    with (
        patch(
            "app.websocket.handler.ws_manager.connect", new=AsyncMock(return_value=True)
        ),
        patch("app.websocket.handler._send_initial_history", new=AsyncMock()),
        patch(
            "app.websocket.handler._redis_forwarder", side_effect=fake_redis_forwarder
        ),
        patch("app.websocket.handler.ws_manager.disconnect"),
        patch("app.main.redis_client", mock_redis),
    ):
        await websocket_endpoint(ws)

    # If we reached here without hanging, sub_task was properly cancelled


# ---------------------------------------------------------------------------
# _handle_command – all branches (already partly covered; test unknown command here)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_command_invalid_json():
    ws = _make_ws()
    await _handle_command(ws, "not json{{")
    sent = ws.send_text.call_args[0][0]
    data = json.loads(sent)
    assert data["type"] == "error"
    assert "Invalid JSON" in data["detail"]


@pytest.mark.asyncio
async def test_handle_command_unknown_command():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "unknown_cmd"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["type"] == "error"
    assert "unknown_cmd" in sent["detail"]


@pytest.mark.asyncio
async def test_handle_command_pause():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "pause"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["type"] == "ack"
    assert sent["command"] == "pause"


@pytest.mark.asyncio
async def test_handle_command_resume():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "resume"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["command"] == "resume"


@pytest.mark.asyncio
async def test_handle_command_set_speed():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "set_speed", "speed": 2.5}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["speed"] == 2.5


@pytest.mark.asyncio
async def test_handle_command_replay():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "replay"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["status"] == "not_implemented"


@pytest.mark.asyncio
async def test_handle_command_ping():
    ws = _make_ws()
    await _handle_command(ws, json.dumps({"command": "ping"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["type"] == "pong"


@pytest.mark.asyncio
async def test_handle_command_stats():
    ws = _make_ws()
    with patch("app.websocket.handler.anomaly_detector") as mock_ad:
        mock_ad.get_stats.return_value = {"rate": 5.0}
        await _handle_command(ws, json.dumps({"command": "stats"}))
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["type"] == "stats"
    assert sent["data"]["rate"] == 5.0


# ---------------------------------------------------------------------------
# _send_initial_history – processor paths covered here for completeness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_initial_history_with_processor():
    """_send_initial_history sends an 'init' message with recent events."""
    from app.websocket.handler import _send_initial_history

    ws = _make_ws()
    events = [{"id": "e1", "attack_type": "DDoS"}]

    mock_proc = MagicMock()
    mock_proc.get_recent_events = MagicMock(return_value=events)

    with (
        patch("app.main.processor", mock_proc),
        patch("app.websocket.handler.anomaly_detector") as mock_ad,
        patch("app.websocket.handler.ws_manager") as mock_wsm,
    ):
        mock_ad.get_stats.return_value = {}
        mock_wsm.get_connection_count.return_value = 3
        await _send_initial_history(ws)

    ws.send_text.assert_called_once()
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["type"] == "init"
    assert len(payload["events"]) == 1
    assert payload["connection_count"] == 3


@pytest.mark.asyncio
async def test_send_initial_history_no_processor():
    """_send_initial_history sends an empty events list when processor is None."""
    from app.websocket.handler import _send_initial_history

    ws = _make_ws()

    with (
        patch("app.main.processor", None),
        patch("app.websocket.handler.anomaly_detector") as mock_ad,
        patch("app.websocket.handler.ws_manager") as mock_wsm,
    ):
        mock_ad.get_stats.return_value = {}
        mock_wsm.get_connection_count.return_value = 0
        await _send_initial_history(ws)

    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["events"] == []


@pytest.mark.asyncio
async def test_send_initial_history_exception_is_swallowed():
    """If sending raises, the error is swallowed and no exception propagates."""
    from app.websocket.handler import _send_initial_history

    ws = _make_ws()
    ws.send_text = AsyncMock(side_effect=RuntimeError("send failed"))

    with (
        patch("app.main.processor", None),
        patch("app.websocket.handler.anomaly_detector") as mock_ad,
        patch("app.websocket.handler.ws_manager") as mock_wsm,
    ):
        mock_ad.get_stats.return_value = {}
        mock_wsm.get_connection_count.return_value = 0
        # Should not raise
        await _send_initial_history(ws)
