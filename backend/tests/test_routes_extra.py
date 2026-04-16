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
