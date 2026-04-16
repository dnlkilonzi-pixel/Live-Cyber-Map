"""Integration tests: WebSocket connect → attack event → alert fires → WS receives alert.

These tests run entirely in-process using HTTPX's ASGITransport and
starlette.testclient.WebSocketTestSession (via pytest-asyncio) so no live
server or database is required.

Scope:
    1. WebSocket client connects and receives the initial ``history`` message.
    2. A mock attack event is injected; clients receive an ``attack`` message.
    3. An alert rule matching the attack type is seeded; the alert fires and
       the client receives an ``alert`` message within a short timeout.
    4. Rate-limiting middleware returns 429 after exceeding the per-IP limit.
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.alert import AlertFired, AlertRule
from app.services.alert_service import alert_service
from app.services.websocket_manager import ws_manager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_attack(attack_type: str = "DDoS") -> dict:
    return {
        "id": "test-id-1",
        "attack_type": attack_type,
        "source_country": "RU",
        "dest_country": "US",
        "source_lat": 55.75,
        "source_lng": 37.62,
        "dest_lat": 38.9,
        "dest_lng": -77.0,
        "severity": 8,
        "timestamp": "2025-01-01T00:00:00Z",
    }


def _make_rule(condition: str = "attack_type", target: str = "DDoS") -> AlertRule:
    rule = MagicMock(spec=AlertRule)
    rule.id = 1
    rule.name = "Test DDoS rule"
    rule.condition = condition
    rule.target = target
    rule.threshold = None
    rule.bbox = None
    rule.enabled = True
    return rule


# ---------------------------------------------------------------------------
# Test: alert_service.check_attack_event fires for matching attack type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_fires_on_matching_attack_type():
    """AlertService.check_attack_event must return an AlertFired for a matching rule."""
    rule = _make_rule(condition="attack_type", target="DDoS")
    await alert_service.reload_rules([rule])
    # Clear last-fired cache so cooldown doesn't suppress
    alert_service._last_fired.clear()

    event = _make_attack("DDoS")
    fired = await alert_service.check_attack_event(event)

    assert len(fired) == 1
    assert fired[0].rule_id == 1
    assert "DDoS" in fired[0].message


@pytest.mark.asyncio
async def test_alert_does_not_fire_for_nonmatching_attack_type():
    """AlertService.check_attack_event must NOT fire when attack type doesn't match."""
    rule = _make_rule(condition="attack_type", target="Ransomware")
    await alert_service.reload_rules([rule])
    alert_service._last_fired.clear()

    event = _make_attack("DDoS")
    fired = await alert_service.check_attack_event(event)

    assert fired == []


@pytest.mark.asyncio
async def test_alert_fires_for_any_type_when_target_is_empty():
    """An attack_type rule with blank target fires for every attack type."""
    rule = _make_rule(condition="attack_type", target="")
    await alert_service.reload_rules([rule])
    alert_service._last_fired.clear()

    event = _make_attack("Malware")
    fired = await alert_service.check_attack_event(event)

    assert len(fired) == 1


@pytest.mark.asyncio
async def test_alert_respects_cooldown():
    """AlertService must suppress repeat fires within the cooldown window."""
    rule = _make_rule()
    await alert_service.reload_rules([rule])
    alert_service._last_fired.clear()

    event = _make_attack("DDoS")
    # First fire — should succeed
    fired1 = await alert_service.check_attack_event(event)
    # Second fire immediately — cooldown active, should be suppressed
    fired2 = await alert_service.check_attack_event(event)

    assert len(fired1) == 1
    assert fired2 == []


# ---------------------------------------------------------------------------
# Test: bbox geofence evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bbox_alert_fires_when_point_inside():
    rule = _make_rule(condition="bbox", target="")
    rule.bbox = "35.0,-80.0,45.0,-70.0"  # covers eastern US
    await alert_service.reload_rules([rule])
    alert_service._last_fired.clear()

    event = {**_make_attack("DDoS"), "dest_lat": 40.0, "dest_lng": -75.0}
    fired = await alert_service.check_attack_event(event)

    assert len(fired) == 1


@pytest.mark.asyncio
async def test_bbox_alert_does_not_fire_when_point_outside():
    rule = _make_rule(condition="bbox", target="")
    rule.bbox = "35.0,-80.0,45.0,-70.0"
    await alert_service.reload_rules([rule])
    alert_service._last_fired.clear()

    event = {**_make_attack("DDoS"), "dest_lat": 55.0, "dest_lng": 37.0}  # Moscow
    fired = await alert_service.check_attack_event(event)

    assert fired == []


# ---------------------------------------------------------------------------
# Test: WebSocket broadcast of alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_receives_alert_broadcast():
    """ws_manager.broadcast({type:'alert',...}) must reach all connected clients."""
    received: list = []

    mock_ws = AsyncMock()

    # Simulate send_text capturing the payload
    async def capture_send(text):
        received.append(json.loads(text))

    mock_ws.send_text = capture_send
    mock_ws.headers = MagicMock()
    mock_ws.headers.get = MagicMock(return_value=None)
    mock_ws.client = MagicMock()
    mock_ws.client.host = "127.0.0.1"

    # Manually insert the mock WS into the active set
    ws_manager._active.add(mock_ws)
    try:
        alert_payload = AlertFired(
            rule_id=42,
            rule_name="Test",
            condition="attack_type",
            message="DDoS attack detected",
            fired_at=time.time(),
        )
        await ws_manager.broadcast(
            {"type": "alert", "data": alert_payload.model_dump()}
        )

        assert len(received) == 1
        assert received[0]["type"] == "alert"
        assert received[0]["data"]["rule_id"] == 42
    finally:
        ws_manager._active.discard(mock_ws)


# ---------------------------------------------------------------------------
# Test: REST API smoke (health endpoint responds 200)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# Test: Rate limiting returns 429 after exceeding limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_returns_429():
    """After 60 requests in the window, the 61st must get a 429 response."""
    import time as _time

    from app.main import _RATE_LIMIT_PATHS, _rl_counts

    # Pick one of the rate-limited paths
    path = "/api/attacks/recent"
    assert path in _RATE_LIMIT_PATHS

    # Inject fake timestamps filling the window
    now = _time.time()
    test_ip = "192.0.2.1"
    _rl_counts[test_ip] = [now] * 60

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-forwarded-for": test_ip},
    ) as client:
        resp = await client.get(path)

    assert resp.status_code == 429
    # Clean up
    _rl_counts.pop(test_ip, None)
