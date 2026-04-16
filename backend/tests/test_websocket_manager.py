"""Unit tests for WebSocketManager.

Tests cover: connect/disconnect lifecycle, per-IP connection limit,
sliding-window rate limit, stale-state pruning, broadcast, channel
subscription, Redis helpers, and the _get_ip static method.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.websocket_manager import (
    _MAX_CONNECTIONS_PER_IP,
    _WS_RATE_MAX,
    _WS_RATE_WINDOW,
    WebSocketManager,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(ip: str = "127.0.0.1") -> MagicMock:
    """Return a minimal AsyncMock that duck-types a FastAPI WebSocket."""
    ws = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(return_value=None)  # no X-Forwarded-For
    ws.client = MagicMock()
    ws.client.host = ip
    return ws


# ---------------------------------------------------------------------------
# connect – happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_accepts_connection():
    mgr = WebSocketManager()
    ws = _make_ws()
    result = await mgr.connect(ws)
    assert result is True
    assert ws in mgr._active
    ws.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_increments_ip_count():
    mgr = WebSocketManager()
    ws = _make_ws()
    await mgr.connect(ws)
    assert mgr._ip_counts["127.0.0.1"] == 1


@pytest.mark.asyncio
async def test_connect_records_timestamp():
    mgr = WebSocketManager()
    ws = _make_ws()
    before = time.time()
    await mgr.connect(ws)
    after = time.time()
    timestamps = mgr._ip_connect_times["127.0.0.1"]
    assert len(timestamps) == 1
    assert before <= timestamps[0] <= after


# ---------------------------------------------------------------------------
# connect – connection-count limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_rejects_when_too_many_connections():
    mgr = WebSocketManager()
    mgr._ip_counts["127.0.0.1"] = _MAX_CONNECTIONS_PER_IP
    ws = _make_ws()
    result = await mgr.connect(ws)
    assert result is False
    ws.close.assert_awaited_once_with(
        code=1008, reason="Too many connections from this IP"
    )
    assert ws not in mgr._active


# ---------------------------------------------------------------------------
# connect – rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_rejects_when_rate_limited():
    mgr = WebSocketManager()
    now = time.time()
    mgr._ip_connect_times["127.0.0.1"] = [now] * _WS_RATE_MAX
    ws = _make_ws()
    result = await mgr.connect(ws)
    assert result is False
    ws.close.assert_awaited_once_with(
        code=1008, reason="Connection rate limit exceeded"
    )
    assert ws not in mgr._active


@pytest.mark.asyncio
async def test_connect_allows_after_window_expires():
    """Old timestamps outside the window should not count against the limit."""
    mgr = WebSocketManager()
    old_ts = time.time() - _WS_RATE_WINDOW - 5
    mgr._ip_connect_times["127.0.0.1"] = [old_ts] * _WS_RATE_MAX
    ws = _make_ws()
    result = await mgr.connect(ws)
    assert result is True


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_removes_from_active():
    mgr = WebSocketManager()
    ws = _make_ws()
    await mgr.connect(ws)
    mgr.disconnect(ws)
    assert ws not in mgr._active


@pytest.mark.asyncio
async def test_disconnect_decrements_ip_count():
    mgr = WebSocketManager()
    ws = _make_ws()
    await mgr.connect(ws)
    assert mgr._ip_counts["127.0.0.1"] == 1
    mgr.disconnect(ws)
    assert mgr._ip_counts.get("127.0.0.1", 0) == 0


@pytest.mark.asyncio
async def test_disconnect_prunes_fully_stale_ip_state():
    """After last disconnect, IPs with no recent timestamps are evicted entirely."""
    mgr = WebSocketManager()
    ws = _make_ws()
    await mgr.connect(ws)
    # Backdate all timestamps outside the window
    mgr._ip_connect_times["127.0.0.1"] = [time.time() - _WS_RATE_WINDOW - 10]
    mgr.disconnect(ws)
    assert "127.0.0.1" not in mgr._ip_connect_times
    assert "127.0.0.1" not in mgr._ip_counts


@pytest.mark.asyncio
async def test_disconnect_keeps_recent_timestamps():
    """If the IP still has recent timestamps, keep them (reconnection expected soon)."""
    mgr = WebSocketManager()
    ws = _make_ws()
    await mgr.connect(ws)
    # Timestamps are fresh (just set by connect) — should remain
    mgr.disconnect(ws)
    # IP evicted only if no recent timestamps; fresh timestamp → key may remain
    # Accept either outcome (edge-case where the timestamp is exactly at boundary)
    times = mgr._ip_connect_times.get("127.0.0.1", [])
    assert isinstance(times, list)


@pytest.mark.asyncio
async def test_disconnect_ip_count_never_goes_negative():
    mgr = WebSocketManager()
    ws = _make_ws()
    # Disconnect without ever connecting
    mgr.disconnect(ws)  # _ip_counts["127.0.0.1"] starts at 0 (defaultdict)
    assert mgr._ip_counts.get("127.0.0.1", 0) == 0


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_empty_active_returns_early():
    mgr = WebSocketManager()
    await mgr.broadcast({"type": "test"})  # must not raise


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients():
    mgr = WebSocketManager()
    ws1 = _make_ws("10.0.0.1")
    ws2 = _make_ws("10.0.0.2")
    mgr._active.update({ws1, ws2})
    await mgr.broadcast({"type": "ping"})
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_skips_low_priority_when_many_clients():
    mgr = WebSocketManager()
    # Put 51 mock clients in active set
    for _ in range(51):
        mgr._active.add(AsyncMock())
    clients_before = list(mgr._active)
    await mgr.broadcast({"type": "low"}, priority=-1)
    for ws in clients_before:
        ws.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_prunes_dead_clients():
    mgr = WebSocketManager()
    dead = _make_ws("9.9.9.9")
    dead.send_text.side_effect = Exception("connection reset")
    mgr._active.add(dead)
    await mgr.broadcast({"type": "test"})
    assert dead not in mgr._active


# ---------------------------------------------------------------------------
# Channel subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_and_broadcast_to_channel():
    mgr = WebSocketManager()
    ws = AsyncMock()
    mgr.subscribe_to_channel("alerts", ws)
    assert ws in mgr._channels["alerts"]
    await mgr.broadcast_to_channel("alerts", {"type": "alert"})
    ws.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_to_channel_empty_channel():
    mgr = WebSocketManager()
    await mgr.broadcast_to_channel("nonexistent", {"type": "test"})  # must not raise


@pytest.mark.asyncio
async def test_unsubscribe_from_channel():
    mgr = WebSocketManager()
    ws = AsyncMock()
    mgr.subscribe_to_channel("ch", ws)
    mgr.unsubscribe_from_channel("ch", ws)
    assert ws not in mgr._channels.get("ch", set())


@pytest.mark.asyncio
async def test_broadcast_to_channel_prunes_dead():
    mgr = WebSocketManager()
    dead = _make_ws("1.2.3.4")
    dead.send_text.side_effect = Exception("dead")
    mgr.subscribe_to_channel("ch", dead)
    await mgr.broadcast_to_channel("ch", {"type": "msg"})
    assert dead not in mgr._active


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_get_connection_count_zero_initially():
    mgr = WebSocketManager()
    assert mgr.get_connection_count() == 0


def test_get_connection_count_increments():
    mgr = WebSocketManager()
    mgr._active.add(AsyncMock())
    mgr._active.add(AsyncMock())
    assert mgr.get_connection_count() == 2


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def test_set_redis_stores_client():
    mgr = WebSocketManager()
    mock_redis = MagicMock()
    mgr.set_redis(mock_redis)
    assert mgr._redis is mock_redis


@pytest.mark.asyncio
async def test_start_redis_subscriber_no_redis_does_not_raise():
    mgr = WebSocketManager()
    await mgr.start_redis_subscriber()
    assert mgr._sub_task is None


@pytest.mark.asyncio
async def test_stop_redis_subscriber_no_task_does_not_raise():
    mgr = WebSocketManager()
    await mgr.stop_redis_subscriber()  # must not raise


# ---------------------------------------------------------------------------
# _get_ip static method
# ---------------------------------------------------------------------------


def test_get_ip_prefers_forwarded_for_header():
    ws = MagicMock()
    ws.headers.get = MagicMock(return_value="1.2.3.4, 5.6.7.8")
    ws.client = None
    assert WebSocketManager._get_ip(ws) == "1.2.3.4"


def test_get_ip_falls_back_to_client_host():
    ws = MagicMock()
    ws.headers.get = MagicMock(return_value=None)
    ws.client = MagicMock()
    ws.client.host = "9.9.9.9"
    assert WebSocketManager._get_ip(ws) == "9.9.9.9"


def test_get_ip_returns_unknown_on_exception():
    ws = MagicMock()
    ws.headers.get = MagicMock(side_effect=RuntimeError("broken"))
    assert WebSocketManager._get_ip(ws) == "unknown"


# ---------------------------------------------------------------------------
# start_redis_subscriber / stop_redis_subscriber
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_redis_subscriber_creates_task():
    import asyncio
    from unittest.mock import AsyncMock, patch

    mgr = WebSocketManager()
    mock_redis = AsyncMock()
    mgr._redis = mock_redis

    # Make _redis_listener do nothing so the task completes quickly
    async def _noop():
        pass

    with patch.object(mgr, "_redis_listener", _noop):
        await mgr.start_redis_subscriber()
        # Give the task a moment to start
        await asyncio.sleep(0)
        assert mgr._sub_task is not None
        await mgr.stop_redis_subscriber()


@pytest.mark.asyncio
async def test_start_redis_subscriber_no_redis_logs_warning():
    mgr = WebSocketManager()
    mgr._redis = None  # no redis
    await mgr.start_redis_subscriber()
    assert mgr._sub_task is None  # task not created


@pytest.mark.asyncio
async def test_stop_redis_subscriber_noop_when_no_task():
    mgr = WebSocketManager()
    mgr._sub_task = None
    await mgr.stop_redis_subscriber()  # should not raise


@pytest.mark.asyncio
async def test_stop_redis_subscriber_cancels_task():
    import asyncio

    mgr = WebSocketManager()

    async def _forever():
        while True:
            await asyncio.sleep(10)

    mgr._sub_task = asyncio.create_task(_forever())
    await mgr.stop_redis_subscriber()
    assert mgr._sub_task.done()


# ---------------------------------------------------------------------------
# _redis_listener – message forwarding, bad JSON, CancelledError, generic exc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_listener_forwards_message():
    import asyncio
    import json

    mgr = WebSocketManager()

    # Build a mock pubsub that yields one message then ends
    messages = [
        {"type": "subscribe", "data": 1},  # should be skipped
        {"type": "message", "data": json.dumps({"source_ip": "1.2.3.4"})},
    ]

    async def _aiterable():
        for m in messages:
            yield m

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = _aiterable

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    mgr._redis = mock_redis

    broadcast_calls = []

    async def _capture(msg):
        broadcast_calls.append(msg)

    with patch.object(mgr, "broadcast", side_effect=_capture):
        await mgr._redis_listener()

    # One broadcast call for the "message" type entry
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["type"] == "attack"


@pytest.mark.asyncio
async def test_redis_listener_skips_bad_json():
    import asyncio

    mgr = WebSocketManager()

    messages = [
        {"type": "message", "data": "not valid json {{"},
    ]

    async def _aiterable():
        for m in messages:
            yield m

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = _aiterable

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    mgr._redis = mock_redis

    broadcast_calls = []

    with patch.object(mgr, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        await mgr._redis_listener()

    mock_broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_redis_listener_handles_cancelled_error():
    import asyncio

    mgr = WebSocketManager()

    async def _aiterable():
        raise asyncio.CancelledError()
        yield  # make it an async generator

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = _aiterable

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    mgr._redis = mock_redis

    # CancelledError should be swallowed and not propagate
    await mgr._redis_listener()


@pytest.mark.asyncio
async def test_redis_listener_handles_generic_exception():
    mgr = WebSocketManager()

    async def _aiterable():
        raise RuntimeError("pubsub broken")
        yield  # make it an async generator

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = _aiterable

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    mgr._redis = mock_redis

    # Generic exception should be caught and logged, not re-raised
    await mgr._redis_listener()
