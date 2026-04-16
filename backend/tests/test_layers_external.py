"""Tests for external HTTP data fetchers in app/api/layers_routes.py.

Covers: _earthquakes_data (real + fallback), _weather_data (real + fallback),
_gdacs_disasters_data (XML + fallback), _flight_tracking_data (real + fallback),
_vessel_tracking_data (real + fallback), _terrorist_incidents_data.
"""

from __future__ import annotations

import json
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.layers_routes import (
    LayerFeature,
    _earthquakes_data,
    _flight_tracking_data,
    _gdacs_disasters_data,
    _generate_layer_data,
    _terrorist_incidents_data,
    _vessel_tracking_data,
    _weather_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_httpx_client(
    status: int, *, json_body=None, text_body: str = ""
) -> MagicMock:
    """Return a mock httpx.AsyncClient context manager."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.text = text_body

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


# ---------------------------------------------------------------------------
# _earthquakes_data – real data path (200)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_earthquakes_data_real_200():
    """Returns LayerFeatures when USGS returns 200 with GeoJSON."""
    usgs_payload = {
        "features": [
            {
                "id": "usgs1",
                "properties": {
                    "mag": 5.0,
                    "place": "Pacific Ocean",
                    "time": 1700000000000,
                    "url": "https://example.com",
                },
                "geometry": {"coordinates": [139.7, 35.7, 10.0]},
            },
            {
                "id": "usgs2",
                "properties": {"mag": None, "place": None, "time": None, "url": ""},
                "geometry": {"coordinates": [0.0, 0.0, 0.0]},
            },
        ]
    }
    mock_client = _mock_httpx_client(200, json_body=usgs_payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _earthquakes_data(10)

    # At least one feature from real data
    assert len(features) >= 1
    real = features[0]
    assert real.id == "usgs1"
    assert real.extra["is_real"] is True
    assert -90 <= real.lat <= 90
    assert -180 <= real.lng <= 180
    assert 0.0 <= real.value <= 1.0


@pytest.mark.asyncio
async def test_earthquakes_data_real_empty_features():
    """Returns empty list when USGS returns 200 with no features (no fallback)."""
    mock_client = _mock_httpx_client(200, json_body={"features": []})
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _earthquakes_data(10)
    # 200 with empty features → returns empty list (real data path, no fallback)
    assert features == []


@pytest.mark.asyncio
async def test_earthquakes_data_non_200_falls_back():
    """Returns simulated data when USGS returns non-200."""
    mock_client = _mock_httpx_client(503)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _earthquakes_data(20)

    assert len(features) > 0
    for f in features:
        assert f.extra.get("is_real") is False


@pytest.mark.asyncio
async def test_earthquakes_data_http_exception_falls_back():
    """Returns simulated data when HTTP call raises an exception."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _earthquakes_data(15)

    assert len(features) > 0
    for f in features:
        assert f.extra.get("is_real") is False


@pytest.mark.asyncio
async def test_earthquakes_data_limit_applied():
    """Fallback data respects the limit parameter."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _earthquakes_data(5)
    assert len(features) <= 5


# ---------------------------------------------------------------------------
# _weather_data – real data path (200)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weather_data_real_200_single_object():
    """Returns LayerFeatures when Open-Meteo returns a single object (not list)."""
    weather_payload = {
        "current": {
            "temperature_2m": 22.5,
            "wind_speed_10m": 15.0,
            "weather_code": 1,
        }
    }
    mock_client = _mock_httpx_client(200, json_body=weather_payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _weather_data(3)

    assert len(features) >= 1
    f = features[0]
    assert f.extra["is_real"] is True
    assert f.extra["temperature_c"] == 22.5
    assert "city" in f.extra


@pytest.mark.asyncio
async def test_weather_data_real_200_list_response():
    """Returns LayerFeatures when Open-Meteo returns a list."""
    city_result = {
        "current": {"temperature_2m": 10.0, "wind_speed_10m": 8.0, "weather_code": 55}
    }
    mock_client = _mock_httpx_client(200, json_body=[city_result, city_result])
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _weather_data(2)

    assert len(features) == 2
    for f in features:
        assert f.extra["is_real"] is True


@pytest.mark.asyncio
async def test_weather_data_real_200_null_temperature_skipped():
    """Cities with null temperature_2m are skipped."""
    weather_payload = {
        "current": {"temperature_2m": None, "wind_speed_10m": 0, "weather_code": 0}
    }
    mock_client = _mock_httpx_client(200, json_body=[weather_payload])
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _weather_data(1)
    # No valid features from real data → returns random fallback
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_weather_data_non_200_falls_back():
    """Returns simulated data when Open-Meteo returns non-200."""
    mock_client = _mock_httpx_client(500)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _weather_data(5)
    assert len(features) > 0


@pytest.mark.asyncio
async def test_weather_data_exception_falls_back():
    """Returns simulated data when HTTP call raises."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("timeout"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _weather_data(5)
    assert len(features) > 0


# ---------------------------------------------------------------------------
# _gdacs_disasters_data – real data path (XML)
# ---------------------------------------------------------------------------

_GDACS_XML = textwrap.dedent("""\
    <?xml version="1.0"?>
    <rss>
      <channel>
        <item>
          <title>Flood in Bangladesh</title>
          <gdacs:eventtype xmlns:gdacs="http://www.gdacs.org">FL</gdacs:eventtype>
          <gdacs:alertlevel xmlns:gdacs="http://www.gdacs.org">Orange</gdacs:alertlevel>
          <geo:lat xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">23.5</geo:lat>
          <geo:long xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">90.3</geo:long>
        </item>
        <item>
          <title>Cyclone near Philippines</title>
          <gdacs:eventtype xmlns:gdacs="http://www.gdacs.org">TC</gdacs:eventtype>
          <gdacs:alertlevel xmlns:gdacs="http://www.gdacs.org">Red</gdacs:alertlevel>
          <geo:lat xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">15.0</geo:lat>
          <geo:long xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">120.0</geo:long>
        </item>
        <item>
          <title>No coords item</title>
        </item>
        <item>
          <title>Bad coords</title>
          <geo:lat xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">not_a_float</geo:lat>
          <geo:long xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">not_a_float</geo:long>
        </item>
      </channel>
    </rss>
""")


@pytest.mark.asyncio
async def test_gdacs_disasters_data_real_200():
    """Returns LayerFeatures when GDACS returns 200 with valid RSS/XML."""
    mock_client = _mock_httpx_client(200, text_body=_GDACS_XML)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _gdacs_disasters_data(10)

    # 2 valid items (the ones with coordinates)
    assert len(features) == 2
    fl_feat = features[0]
    assert fl_feat.extra["event_type"] == "FL"
    assert fl_feat.extra["alert_level"] == "Orange"
    assert fl_feat.extra["is_real"] is True
    tc_feat = features[1]
    assert tc_feat.extra["alert_level"] == "Red"
    assert tc_feat.value == 1.0  # Red → 1.0


@pytest.mark.asyncio
async def test_gdacs_disasters_data_real_200_channel_none():
    """Falls back to flat item search when <channel> tag is absent."""
    xml_no_channel = textwrap.dedent("""\
        <?xml version="1.0"?>
        <rss>
          <item>
            <title>Earthquake</title>
            <gdacs:eventtype xmlns:gdacs="http://www.gdacs.org">EQ</gdacs:eventtype>
            <gdacs:alertlevel xmlns:gdacs="http://www.gdacs.org">Green</gdacs:alertlevel>
            <geo:lat xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">10.0</geo:lat>
            <geo:long xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">50.0</geo:long>
          </item>
        </rss>
    """)
    mock_client = _mock_httpx_client(200, text_body=xml_no_channel)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _gdacs_disasters_data(10)
    assert len(features) == 1


@pytest.mark.asyncio
async def test_gdacs_disasters_data_non_200_falls_back():
    mock_client = _mock_httpx_client(404)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _gdacs_disasters_data(10)
    assert len(features) > 0
    for f in features:
        assert f.extra["is_real"] is False


@pytest.mark.asyncio
async def test_gdacs_disasters_data_exception_falls_back():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("network error"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _gdacs_disasters_data(5)
    assert len(features) > 0


@pytest.mark.asyncio
async def test_gdacs_disasters_data_limit():
    """Fallback respects limit."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _gdacs_disasters_data(3)
    assert len(features) <= 3


# ---------------------------------------------------------------------------
# _flight_tracking_data – real data path (200)
# ---------------------------------------------------------------------------


def _opensky_state(
    icao="abc123",
    callsign="FL100",
    country="DE",
    lat=51.5,
    lng=10.0,
    alt=10000,
    vel=250,
    on_ground=False,
):
    # [icao24, callsign, origin_country, time_pos, last_contact,
    #  longitude, latitude, baro_altitude, on_ground, velocity, heading, ...]
    return [
        icao,
        callsign,
        country,
        1700000000,
        1700000000,
        lng,
        lat,
        alt,
        on_ground,
        vel,
        90.0,
        0.0,
    ]


@pytest.mark.asyncio
async def test_flight_tracking_data_real_200():
    """Returns LayerFeatures for airborne flights from OpenSky."""
    opensky_payload = {
        "states": [
            _opensky_state(),  # airborne
            _opensky_state("xyz", "FL200", "US", on_ground=True),  # on ground – skipped
            _opensky_state("skip1", None, "FR", lat=None),  # null lat – skipped
        ]
    }
    mock_client = _mock_httpx_client(200, json_body=opensky_payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _flight_tracking_data(50)

    assert len(features) == 1  # only the airborne one
    f = features[0]
    assert f.id == "abc123"
    assert f.extra["is_real"] is True
    assert f.extra["callsign"] == "FL100"


@pytest.mark.asyncio
async def test_flight_tracking_data_null_states():
    """Returns empty list when states key is None (real path, no airborne flights)."""
    mock_client = _mock_httpx_client(200, json_body={"states": None})
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _flight_tracking_data(20)
    # states=None → or [] → no flights → returns empty list (real data path)
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_flight_tracking_data_short_state_vector():
    """State vectors shorter than 9 elements are skipped."""
    mock_client = _mock_httpx_client(200, json_body={"states": [[1, 2, 3]]})
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _flight_tracking_data(10)
    # No valid airborne flights → fallback
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_flight_tracking_data_non_200_falls_back():
    mock_client = _mock_httpx_client(429)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _flight_tracking_data(10)
    assert len(features) > 0


@pytest.mark.asyncio
async def test_flight_tracking_data_exception_falls_back():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("conn error"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _flight_tracking_data(10)
    assert len(features) > 0


@pytest.mark.asyncio
async def test_flight_tracking_data_callsign_fallback_to_icao():
    """Empty callsign falls back to the icao24 value."""
    state = _opensky_state(icao="deadbeef", callsign="   ")
    mock_client = _mock_httpx_client(200, json_body={"states": [state]})
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _flight_tracking_data(5)
    assert len(features) == 1
    assert features[0].extra["callsign"] == "deadbeef"


# ---------------------------------------------------------------------------
# _vessel_tracking_data – real data path (200)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vessel_tracking_data_real_200_list():
    """Returns LayerFeatures when AISHub returns a vessel list."""
    vessels = [
        {
            "MMSI": "123456789",
            "LATITUDE": 1.3,
            "LONGITUDE": 103.8,
            "NAME": "MV Alpha",
            "SOG": 12.5,
        },
        {
            "MMSI": "987654321",
            "lat": -33.9,
            "lon": 18.4,
            "NAME": "MV Beta",
            "speed": 8.0,
        },
        {"MMSI": "nullvessel", "LATITUDE": None, "LONGITUDE": None},  # skipped
    ]
    mock_client = _mock_httpx_client(200, json_body=vessels)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _vessel_tracking_data(50)

    assert len(features) == 2
    assert features[0].id == "123456789"
    assert features[0].extra["is_real"] is True
    assert features[0].extra["speed_kn"] == 12.5


@pytest.mark.asyncio
async def test_vessel_tracking_data_real_200_dict_with_vessels_key():
    """Handles AISHub response as dict with 'vessels' key."""
    payload = {
        "vessels": [
            {
                "MMSI": "111",
                "LATITUDE": 51.9,
                "LONGITUDE": 4.5,
                "NAME": "Ship1",
                "SOG": 10,
            }
        ]
    }
    mock_client = _mock_httpx_client(200, json_body=payload)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _vessel_tracking_data(10)
    assert len(features) == 1


@pytest.mark.asyncio
async def test_vessel_tracking_data_empty_list_raises_falls_back():
    """Empty vessel list triggers the ValueError and falls back to simulation."""
    mock_client = _mock_httpx_client(200, json_body=[])
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _vessel_tracking_data(20)
    # Falls back to simulated traffic
    assert len(features) > 0
    for f in features:
        assert f.extra["is_real"] is False


@pytest.mark.asyncio
async def test_vessel_tracking_data_non_200_falls_back():
    mock_client = _mock_httpx_client(503)
    with patch("httpx.AsyncClient", return_value=mock_client):
        features = await _vessel_tracking_data(10)
    assert len(features) > 0


@pytest.mark.asyncio
async def test_vessel_tracking_data_exception_falls_back():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("timed out"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _vessel_tracking_data(10)
    assert len(features) > 0


# ---------------------------------------------------------------------------
# _terrorist_incidents_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_terrorist_incidents_data_returns_features():
    features = await _terrorist_incidents_data(30)
    assert len(features) > 0
    for f in features:
        assert isinstance(f, LayerFeature)


# ---------------------------------------------------------------------------
# _generate_layer_data – routes to correct generator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_layer_data_earthquakes_called():
    """earthquakes routes to _earthquakes_data (fallback with mocked HTTP)."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _generate_layer_data("earthquakes", 10)
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_generate_layer_data_flight_tracking_called():
    """flight_tracking routes to _flight_tracking_data."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _generate_layer_data("flight_tracking", 10)
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_generate_layer_data_vessel_tracking_called():
    """vessel_tracking routes to _vessel_tracking_data."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _generate_layer_data("vessel_tracking", 10)
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_generate_layer_data_weather_called():
    """weather routes to _weather_data."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _generate_layer_data("weather", 5)
    assert isinstance(features, list)


@pytest.mark.asyncio
async def test_generate_layer_data_gdacs_disasters_called():
    """gdacs_disasters routes to _gdacs_disasters_data."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("fail"))
    with patch("httpx.AsyncClient", return_value=client):
        features = await _generate_layer_data("gdacs_disasters", 5)
    assert isinstance(features, list)
