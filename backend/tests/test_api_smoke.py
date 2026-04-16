"""Basic smoke tests for the FastAPI backend.

These run entirely in-process using an in-memory SQLite database – no
external services (Postgres, Redis, Ollama) are required.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.database import Base, get_db


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
        from app.models import attack, alert, intelligence, financial  # noqa: F401
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
