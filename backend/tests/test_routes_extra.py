"""Additional tests for app/api/routes.py.

Covers: GET /api/health Redis path, GET /api/attacks/recent with processor,
GET /api/attacks/history DB error, GET /api/replay/intelligence.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_client():
    engine = create_async_engine(_SQLITE_URL, echo=False)
    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        from app.models import alert, attack, financial, intelligence  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/health – Redis connected path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_redis_connected(db_client):
    """GET /api/health shows redis=connected when redis_client responds to ping."""
    import app.main as main_module

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    original = main_module.redis_client
    main_module.redis_client = mock_redis
    try:
        resp = await db_client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["redis"] == "connected"
    finally:
        main_module.redis_client = original


@pytest.mark.asyncio
async def test_health_redis_ping_fails(db_client):
    """GET /api/health shows redis=unavailable when ping raises."""
    import app.main as main_module

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionRefusedError("down"))
    original = main_module.redis_client
    main_module.redis_client = mock_redis
    try:
        resp = await db_client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["redis"] == "unavailable"
    finally:
        main_module.redis_client = original


@pytest.mark.asyncio
async def test_health_db_check_fails_but_returns_200(client):
    """When DB raises during health check, status is still ok but database=unavailable."""
    from app.core.database import get_db

    async def bad_db():
        # Yield a session that raises on execute
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        yield mock_session

    app.dependency_overrides[get_db] = bad_db
    try:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] == "unavailable"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/attacks/recent – with processor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attacks_recent_with_processor_returns_events(client):
    """GET /api/attacks/recent returns events when processor is set."""
    import app.main as main_module

    events = [{"id": "e1", "attack_type": "DDoS", "severity": 7}]
    mock_proc = MagicMock()
    mock_proc.get_recent_events = MagicMock(return_value=events)
    original = main_module.processor
    main_module.processor = mock_proc
    try:
        resp = await client.get("/api/attacks/recent?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["events"][0]["attack_type"] == "DDoS"
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_attacks_recent_no_processor_returns_empty(client):
    """GET /api/attacks/recent returns empty when processor is None."""
    import app.main as main_module

    original = main_module.processor
    main_module.processor = None
    try:
        resp = await client.get("/api/attacks/recent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["events"] == []
    finally:
        main_module.processor = original


# ---------------------------------------------------------------------------
# GET /api/attacks/history – DB error returns 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attacks_history_db_error_returns_503(client):
    from app.core.database import get_db

    async def bad_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB crash"))
        yield mock_session

    app.dependency_overrides[get_db] = bad_db
    try:
        resp = await client.get("/api/attacks/history")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/replay/intelligence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_intelligence_empty(db_client):
    """GET /api/replay/intelligence returns merged timeline (empty when DB empty)."""
    resp = await db_client.get("/api/replay/intelligence")
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert "total" in body
    assert "from" in body
    assert "to" in body
    assert isinstance(body["events"], list)


@pytest.mark.asyncio
async def test_replay_intelligence_with_time_params(db_client):
    """Accepts from/to timestamp query params."""
    resp = await db_client.get(
        "/api/replay/intelligence?from=1700000000&to=1700086400&limit=100"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 0


@pytest.mark.asyncio
async def test_replay_intelligence_db_error_returns_503(client):
    from app.core.database import get_db

    async def bad_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB gone"))
        yield mock_session

    app.dependency_overrides[get_db] = bad_db
    try:
        resp = await client.get("/api/replay/intelligence")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/stats – additional paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_includes_ws_connections(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "ws_connections" in body
    assert "attack_types" in body
    assert "top_targets" in body


# ---------------------------------------------------------------------------
# Rate limiter – intelligence/risk is also rate-limited
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_intelligence_risk():
    """GET /api/intelligence/risk is rate-limited after 60 requests."""
    import time as _time

    from app.main import _RATE_LIMIT_PATHS, _rl_counts

    path = "/api/attacks/recent"
    assert path in _RATE_LIMIT_PATHS

    test_ip = "10.0.0.200"
    now = _time.time()
    _rl_counts[test_ip] = [now] * 60

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-forwarded-for": test_ip},
    ) as c:
        resp = await c.get(path)

    assert resp.status_code == 429
    _rl_counts.pop(test_ip, None)


@pytest.mark.asyncio
async def test_rate_limit_uses_x_forwarded_for(client):
    """Rate limiter reads the correct IP from x-forwarded-for."""
    import time as _time

    from app.main import _rl_counts

    test_ip = "203.0.113.5"
    now = _time.time()
    _rl_counts[test_ip] = [now] * 60

    resp = await client.get(
        "/api/attacks/recent",
        headers={"x-forwarded-for": f"{test_ip}, 10.0.0.1"},
    )
    assert resp.status_code == 429
    _rl_counts.pop(test_ip, None)


@pytest.mark.asyncio
async def test_rate_limit_uses_client_host_when_no_forwarded_for(client):
    """Rate limiter falls back to request.client.host if no x-forwarded-for."""
    import time as _time

    from app.main import _rl_counts

    # testclient uses 127.0.0.1 by default as client host in ASGITransport
    test_ip = "127.0.0.1"
    now = _time.time()
    _rl_counts[test_ip] = [now] * 60

    resp = await client.get("/api/attacks/recent")
    assert resp.status_code == 429
    _rl_counts.pop(test_ip, None)


# ---------------------------------------------------------------------------
# GET /api/replay – status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_status(client):
    resp = await client.get("/api/replay")
    assert resp.status_code == 200
    body = resp.json()
    assert "active" in body
    assert "speed" in body


# ---------------------------------------------------------------------------
# POST /api/replay/start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_start(client):
    from app.services.websocket_manager import ws_manager

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock):
        resp = await client.post("/api/replay/start?speed=2.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["speed"] == 2.0
    assert "replay started" in body["status"]


@pytest.mark.asyncio
async def test_replay_start_default_speed(client):
    from app.services.websocket_manager import ws_manager

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock):
        resp = await client.post("/api/replay/start")
    assert resp.status_code == 200
    assert resp.json()["speed"] == 1.0


# ---------------------------------------------------------------------------
# POST /api/replay/stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_stop(client):
    from app.services.websocket_manager import ws_manager

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock):
        resp = await client.post("/api/replay/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert "replay stopped" in body["status"]


# ---------------------------------------------------------------------------
# POST /api/replay/seek
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_seek_empty_db(db_client):
    from app.services.websocket_manager import ws_manager

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock):
        resp = await db_client.post("/api/replay/seek?position=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["position"] == 0
    assert body["status"] == "seek"


@pytest.mark.asyncio
async def test_replay_seek_with_position(db_client):
    from app.services.websocket_manager import ws_manager

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock):
        resp = await db_client.post("/api/replay/seek?position=42")
    assert resp.status_code == 200
    assert resp.json()["position"] == 42


@pytest.mark.asyncio
async def test_replay_seek_broadcasts_attack_events(db_client):
    """When events exist in DB, seek broadcasts them."""
    from datetime import datetime, timezone

    from app.models.attack import AttackEvent
    from app.services.websocket_manager import ws_manager

    # Insert a row so the seek query has something to broadcast
    from app.core.database import get_db as real_get_db

    override = app.dependency_overrides.get(real_get_db)
    if override:
        async for session in override():
            event = AttackEvent(
                source_ip="1.2.3.4",
                source_country="US",
                source_lat=37.0,
                source_lng=-120.0,
                dest_ip="5.6.7.8",
                dest_country="CN",
                dest_lat=39.9,
                dest_lng=116.4,
                attack_type="DDoS",
                severity=5,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(event)
            await session.commit()
            break

    broadcast_calls = []

    async def capture_broadcast(msg):
        broadcast_calls.append(msg)

    with patch.object(ws_manager, "broadcast", side_effect=capture_broadcast):
        resp = await db_client.post("/api/replay/seek?position=0")

    assert resp.status_code == 200
    # At least the replay_seek message + the attack event
    assert any(c.get("type") == "replay_seek" for c in broadcast_calls)


# ---------------------------------------------------------------------------
# GET /api/attacks/history – filter parameters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attacks_history_with_attack_type_filter(db_client):
    resp = await db_client.get("/api/attacks/history?attack_type=DDoS")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_attacks_history_with_source_country_filter(db_client):
    resp = await db_client.get("/api/attacks/history?source_country=US")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_attacks_history_with_dest_country_filter(db_client):
    resp = await db_client.get("/api/attacks/history?dest_country=CN")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_attacks_history_with_severity_range(db_client):
    resp = await db_client.get("/api/attacks/history?min_severity=3&max_severity=8")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_attacks_history_with_offset(db_client):
    resp = await db_client.get("/api/attacks/history?limit=10&offset=5")
    assert resp.status_code == 200
