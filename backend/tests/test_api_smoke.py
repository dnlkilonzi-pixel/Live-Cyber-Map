"""Basic smoke tests for the FastAPI backend.

These run entirely in-process using an in-memory SQLite database – no
external services (Postgres, Redis, Ollama) are required.
"""

import pytest


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
