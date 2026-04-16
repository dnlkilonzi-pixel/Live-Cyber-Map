"""Basic smoke tests for the FastAPI backend.

These run entirely in-process using an in-memory SQLite database – no
external services (Postgres, Redis, Ollama) are required.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# In-memory SQLite fixture for tests that need real DB operations
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_client():
    """HTTPX client wired to the app with get_db overridden to use SQLite."""
    engine = create_async_engine(_SQLITE_URL, echo=False)
    TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    # Create tables
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.anyio
async def test_health_endpoint_returns_200(client):
    """GET /api/health must return HTTP 200 with a status field."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] == "ok"


@pytest.mark.anyio
async def test_stats_endpoint_returns_200(client):
    """GET /api/stats must return HTTP 200 with rate/topology keys."""
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "rates" in body
    assert "top_attackers" in body


@pytest.mark.anyio
async def test_layers_list_not_empty(client):
    """GET /api/layers must return a non-empty list of layer definitions."""
    resp = await client.get("/api/layers")
    assert resp.status_code == 200
    layers = resp.json()
    assert isinstance(layers, list)
    assert len(layers) > 0
    first = layers[0]
    assert "id" in first
    assert "name" in first
    assert "live" in first


@pytest.mark.anyio
async def test_intelligence_risk_returns_list(client):
    """GET /api/intelligence/risk must return a list (may be empty before data)."""
    resp = await client.get("/api/intelligence/risk")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_replay_status(client):
    """GET /api/replay returns replay state."""
    resp = await client.get("/api/replay")
    assert resp.status_code == 200
    body = resp.json()
    assert "active" in body


@pytest.mark.anyio
async def test_attacks_recent_empty_initially(client):
    """GET /api/attacks/recent returns a valid response structure."""
    resp = await client.get("/api/attacks/recent?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert "count" in body


# ---------------------------------------------------------------------------
# PUT /api/alerts/rules/{id} contract tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_put_alert_rule_happy_path(db_client):
    """PUT /api/alerts/rules/{id} — 200 with updated fields returned."""
    # First create a rule to update
    create_resp = await db_client.post(
        "/api/alerts/rules",
        json={"name": "Original Name", "condition": "attack_type", "enabled": True},
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    # Update name and enabled flag
    put_resp = await db_client.put(
        f"/api/alerts/rules/{rule_id}",
        json={"name": "Updated Name", "enabled": False},
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["name"] == "Updated Name"
    assert body["enabled"] is False
    assert body["id"] == rule_id


@pytest.mark.anyio
async def test_put_alert_rule_not_found(db_client):
    """PUT /api/alerts/rules/{id} with a non-existent ID must return 404."""
    resp = await db_client.put(
        "/api/alerts/rules/99999999",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_put_alert_rule_partial_update_name_only(db_client):
    """PUT /api/alerts/rules/{id} with only 'name' must preserve other fields."""
    # Create rule with threshold and target
    create_resp = await db_client.post(
        "/api/alerts/rules",
        json={"name": "Threshold Rule", "condition": "risk_above", "target": "RU", "threshold": 70.0, "enabled": True},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    rule_id = created["id"]

    # Partial update — only name
    put_resp = await db_client.put(
        f"/api/alerts/rules/{rule_id}",
        json={"name": "Renamed Rule"},
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["name"] == "Renamed Rule"
    # Other fields must be preserved
    assert body["target"] == "RU"
    assert body["threshold"] == 70.0
    assert body["enabled"] is True


# ---------------------------------------------------------------------------
# DELETE /api/alerts/rules/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_alert_rule_happy_path(db_client):
    """DELETE /api/alerts/rules/{id} — 204 No Content on success."""
    create_resp = await db_client.post(
        "/api/alerts/rules",
        json={"name": "To Delete", "condition": "attack_type", "enabled": True},
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    del_resp = await db_client.delete(f"/api/alerts/rules/{rule_id}")
    assert del_resp.status_code == 204


@pytest.mark.anyio
async def test_delete_alert_rule_not_found(db_client):
    """DELETE /api/alerts/rules/{id} with a non-existent ID must return 404."""
    resp = await db_client.delete("/api/alerts/rules/99999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/alerts/rules/{id}/toggle
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_toggle_alert_rule_disables_enabled_rule(db_client):
    """PATCH .../toggle flips an enabled rule to disabled."""
    create_resp = await db_client.post(
        "/api/alerts/rules",
        json={"name": "Toggle Me", "condition": "attack_type", "enabled": True},
    )
    rule_id = create_resp.json()["id"]
    tog_resp = await db_client.patch(f"/api/alerts/rules/{rule_id}/toggle")
    assert tog_resp.status_code == 200
    assert tog_resp.json()["enabled"] is False


@pytest.mark.anyio
async def test_toggle_alert_rule_enables_disabled_rule(db_client):
    """PATCH .../toggle flips a disabled rule to enabled."""
    create_resp = await db_client.post(
        "/api/alerts/rules",
        json={"name": "Toggle Me Off", "condition": "attack_type", "enabled": False},
    )
    rule_id = create_resp.json()["id"]
    tog_resp = await db_client.patch(f"/api/alerts/rules/{rule_id}/toggle")
    assert tog_resp.status_code == 200
    assert tog_resp.json()["enabled"] is True


@pytest.mark.anyio
async def test_toggle_alert_rule_not_found(db_client):
    """PATCH .../toggle on a non-existent rule returns 404."""
    resp = await db_client.patch("/api/alerts/rules/99999999/toggle")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/alerts/rules
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_alert_rules_empty(db_client):
    """GET /api/alerts/rules returns an empty list when no rules exist."""
    resp = await db_client.get("/api/alerts/rules")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_list_alert_rules_returns_created_rules(db_client):
    """GET /api/alerts/rules returns all created rules."""
    for i in range(3):
        await db_client.post(
            "/api/alerts/rules",
            json={"name": f"Rule {i}", "condition": "attack_type", "enabled": True},
        )
    resp = await db_client.get("/api/alerts/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 3


# ---------------------------------------------------------------------------
# POST /api/replay/start  and  POST /api/replay/stop
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_replay_start(client):
    """POST /api/replay/start returns status='replay started'."""
    resp = await client.post("/api/replay/start?speed=2.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replay started"
    assert body["speed"] == 2.0


@pytest.mark.anyio
async def test_replay_stop(client):
    """POST /api/replay/stop returns status='replay stopped'."""
    resp = await client.post("/api/replay/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replay stopped"


@pytest.mark.anyio
async def test_replay_start_default_speed(client):
    """POST /api/replay/start with no speed param defaults to 1.0."""
    resp = await client.post("/api/replay/start")
    assert resp.status_code == 200
    assert resp.json()["speed"] == 1.0


# ---------------------------------------------------------------------------
# Rate-limit middleware – non-limited path passes through
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_non_rate_limited_path_always_passes(client):
    """/api/health is not in _RATE_LIMIT_PATHS — always returns 200."""
    for _ in range(5):
        resp = await client.get("/api/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/health with working DB (covers db_ok=True path in routes.py)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_health_with_db_connected(db_client):
    """GET /api/health with SQLite override — database shows 'connected'."""
    resp = await db_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


# ---------------------------------------------------------------------------
# GET /api/attacks/history — filter combinations
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_attack_history_empty(db_client):
    """GET /api/attacks/history returns an empty list when no events exist."""
    resp = await db_client.get("/api/attacks/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_attack_history_with_attack_type_filter(db_client):
    resp = await db_client.get("/api/attacks/history?attack_type=DDoS")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_attack_history_with_source_country_filter(db_client):
    resp = await db_client.get("/api/attacks/history?source_country=RU")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_attack_history_with_dest_country_filter(db_client):
    resp = await db_client.get("/api/attacks/history?dest_country=US")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_attack_history_with_severity_filter(db_client):
    resp = await db_client.get("/api/attacks/history?min_severity=5&max_severity=9")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_attack_history_with_all_filters(db_client):
    resp = await db_client.get(
        "/api/attacks/history?attack_type=DDoS&source_country=CN"
        "&dest_country=US&min_severity=3&max_severity=8&limit=50&offset=0"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# POST /api/replay/seek
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_replay_seek_at_zero(db_client):
    """POST /api/replay/seek?position=0 returns status=seek."""
    resp = await db_client.post("/api/replay/seek?position=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "seek"
    assert body["position"] == 0


@pytest.mark.anyio
async def test_replay_seek_nonzero_position(db_client):
    resp = await db_client.post("/api/replay/seek?position=10")
    assert resp.status_code == 200
    assert resp.json()["position"] == 10
