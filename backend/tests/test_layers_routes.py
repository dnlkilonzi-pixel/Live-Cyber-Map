"""Tests for the data layers API routes.

Tests cover: GET /api/layers (list all, filter by category), GET /api/layers/categories,
GET /api/layers/{layer_id} (known layers, unknown layer → 404), static data generators
(_conflict_zones_data, _military_bases_data, _nuclear_facilities_data, _data_centers_data,
_submarine_cables_data, _disease_outbreaks_data, _wildfires_data, _piracy_data),
_random_points, and the _wmo_icon helper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.api.layers_routes import (
    LAYER_REGISTRY,
    LayerFeature,
    _random_points,
    _wmo_icon,
    _conflict_zones_data,
    _military_bases_data,
    _nuclear_facilities_data,
    _data_centers_data,
    _submarine_cables_data,
    _disease_outbreaks_data,
    _wildfires_data,
    _piracy_data,
    _country_risk_data,
    _cyber_attacks_data,
    _generate_layer_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# GET /api/layers – list all layers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_layers_returns_all(client):
    resp = await client.get("/api/layers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == len(LAYER_REGISTRY)


@pytest.mark.asyncio
async def test_list_layers_shape(client):
    resp = await client.get("/api/layers")
    first = resp.json()[0]
    for key in ("id", "category", "name", "description", "icon", "color", "live"):
        assert key in first


@pytest.mark.asyncio
async def test_list_layers_filter_by_category(client):
    resp = await client.get("/api/layers?category=security")
    data = resp.json()
    assert all(l["category"] == "security" for l in data)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_list_layers_filter_unknown_category_returns_empty(client):
    resp = await client.get("/api/layers?category=nonexistent_xyz")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/layers/categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_categories(client):
    resp = await client.get("/api/layers/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    cats = data["categories"]
    assert isinstance(cats, list)
    assert "security" in cats
    assert "military" in cats
    assert cats == sorted(cats)  # alphabetically sorted


# ---------------------------------------------------------------------------
# GET /api/layers/{layer_id} – unknown layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_layer_unknown_returns_404(client):
    resp = await client.get("/api/layers/totally_fake_layer_xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/layers/{layer_id} – static layers (no external HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_layer_conflict_zones(client):
    resp = await client.get("/api/layers/conflict_zones")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer_id"] == "conflict_zones"
    assert data["count"] > 0
    feat = data["features"][0]
    assert "lat" in feat and "lng" in feat and "value" in feat


@pytest.mark.asyncio
async def test_get_layer_military_bases(client):
    resp = await client.get("/api/layers/military_bases")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_get_layer_nuclear_facilities(client):
    resp = await client.get("/api/layers/nuclear_facilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_get_layer_data_centers(client):
    resp = await client.get("/api/layers/data_centers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_get_layer_disease_outbreaks(client):
    resp = await client.get("/api/layers/disease_outbreaks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_get_layer_submarine_cables(client):
    resp = await client.get("/api/layers/submarine_cables")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_layer_wildfires(client):
    resp = await client.get("/api/layers/wildfires")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_layer_piracy(client):
    resp = await client.get("/api/layers/piracy")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_layer_response_schema(client):
    """Verify the LayerDataResponse schema on any static layer."""
    resp = await client.get("/api/layers/nuclear_facilities")
    data = resp.json()
    assert "layer_id" in data
    assert "features" in data
    assert "last_updated" in data
    assert "count" in data
    assert data["count"] == len(data["features"])


@pytest.mark.asyncio
async def test_get_layer_limit_param(client):
    """limit query param is forwarded to the generator; response count ≥ 1."""
    resp = await client.get("/api/layers/conflict_zones?limit=200")
    data = resp.json()
    assert data["count"] >= 1


# ---------------------------------------------------------------------------
# Static data generators (direct function calls, faster than HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_zones_data_returns_features():
    features = await _conflict_zones_data(100)
    assert len(features) > 0
    assert all(isinstance(f, LayerFeature) for f in features)
    for f in features:
        assert -90 <= f.lat <= 90
        assert -180 <= f.lng <= 180


@pytest.mark.asyncio
async def test_military_bases_data_limit():
    features = await _military_bases_data(5)
    assert len(features) <= 5


@pytest.mark.asyncio
async def test_nuclear_facilities_data():
    features = await _nuclear_facilities_data(100)
    assert len(features) > 0
    for f in features:
        assert f.value == 0.5
        assert "type" in f.extra


@pytest.mark.asyncio
async def test_data_centers_data_limit():
    features = await _data_centers_data(5)
    assert len(features) <= 5
    for f in features:
        assert "provider" in f.extra


@pytest.mark.asyncio
async def test_submarine_cables_data():
    features = await _submarine_cables_data(100)
    assert len(features) > 0
    for f in features:
        assert f.value == 0.9


@pytest.mark.asyncio
async def test_disease_outbreaks_data():
    features = await _disease_outbreaks_data(100)
    assert len(features) > 0
    for f in features:
        assert 0 <= f.value <= 1


@pytest.mark.asyncio
async def test_wildfires_data():
    features = await _wildfires_data(100)
    assert len(features) > 0
    for f in features:
        assert 0 <= f.value <= 1
        assert "area_ha" in f.extra


@pytest.mark.asyncio
async def test_piracy_data():
    features = await _piracy_data(100)
    assert len(features) > 0
    for f in features:
        assert 0 <= f.value <= 1


@pytest.mark.asyncio
async def test_country_risk_data_returns_features():
    features = await _country_risk_data(200)
    # Country risk service may return zero in test env – just verify no crash
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_cyber_attacks_data_no_processor():
    """With no processor loaded, should return empty list without error."""
    import sys

    fake_main = MagicMock()
    fake_main.processor = None
    old_main = sys.modules.get("app.main")
    sys.modules["app.main"] = fake_main
    try:
        features = await _cyber_attacks_data(50)
    finally:
        if old_main is not None:
            sys.modules["app.main"] = old_main
        else:
            del sys.modules["app.main"]
    assert features == []


# ---------------------------------------------------------------------------
# _generate_layer_data – fallback to _random_points for unmapped layers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_layer_data_unmapped_returns_random_points():
    # Use a layer id that exists in LAYER_REGISTRY but has no specific generator
    # e.g. "tor_exit_nodes"
    features = await _generate_layer_data("tor_exit_nodes", 100)
    assert len(features) > 0
    assert all(isinstance(f, LayerFeature) for f in features)


# ---------------------------------------------------------------------------
# _random_points
# ---------------------------------------------------------------------------


def test_random_points_count():
    pts = _random_points("test_layer", 10)
    assert len(pts) == 10


def test_random_points_deterministic():
    pts1 = _random_points("botnet_activity", 20)
    pts2 = _random_points("botnet_activity", 20)
    # Same seed → same output
    assert [p.lat for p in pts1] == [p.lat for p in pts2]


def test_random_points_different_seeds_differ():
    pts1 = _random_points("layer_a", 5)
    pts2 = _random_points("layer_b", 5)
    assert [p.lat for p in pts1] != [p.lat for p in pts2]


def test_random_points_lat_lng_in_range():
    pts = _random_points("test", 50)
    for p in pts:
        assert -60 <= p.lat <= 75
        assert -180 <= p.lng <= 180


def test_random_points_value_in_range():
    pts = _random_points("test", 50)
    for p in pts:
        assert 0.1 <= p.value <= 1.0


def test_random_points_zero_count():
    pts = _random_points("test", 0)
    assert pts == []


# ---------------------------------------------------------------------------
# _wmo_icon
# ---------------------------------------------------------------------------


def test_wmo_icon_clear():
    assert _wmo_icon(0) == "☀️"


def test_wmo_icon_partly_cloudy():
    for code in (1, 2, 3):
        assert _wmo_icon(code) == "⛅"


def test_wmo_icon_fog():
    for code in (45, 48):
        assert _wmo_icon(code) == "🌫️"


def test_wmo_icon_rain():
    assert _wmo_icon(55) == "🌧️"


def test_wmo_icon_snow():
    assert _wmo_icon(73) == "❄️"


def test_wmo_icon_shower():
    assert _wmo_icon(81) == "🌦️"


def test_wmo_icon_thunderstorm():
    for code in (95, 96, 99):
        assert _wmo_icon(code) == "⛈️"


def test_wmo_icon_unknown_returns_thermometer():
    assert _wmo_icon(999) == "🌡️"
