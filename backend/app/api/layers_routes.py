"""Data layer REST API routes.

Serves data for the 40+ map overlay layers.  Many layers use simulated data
for demonstration; the architecture is designed to swap in live feeds later.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Layer registry
# ---------------------------------------------------------------------------

LAYER_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ---- Cyber / Security ----
    "cyber_attacks": {
        "id": "cyber_attacks", "category": "security",
        "name": "Cyber Attacks", "description": "Live cyber attack arcs",
        "icon": "🛡️", "color": "#ff4444", "live": True,
    },
    "vulnerability_feeds": {
        "id": "vulnerability_feeds", "category": "security",
        "name": "CVE Vulnerability Feed", "description": "Recent NIST CVE disclosures",
        "icon": "🔓", "color": "#ff8800", "live": False,
    },
    "tor_exit_nodes": {
        "id": "tor_exit_nodes", "category": "security",
        "name": "Tor Exit Nodes", "description": "Known Tor exit node locations",
        "icon": "🧅", "color": "#9400d3", "live": False,
    },
    "botnet_activity": {
        "id": "botnet_activity", "category": "security",
        "name": "Botnet Activity", "description": "Estimated botnet concentration",
        "icon": "🤖", "color": "#ff00ff", "live": False,
    },
    # ---- Military / Conflict ----
    "conflict_zones": {
        "id": "conflict_zones", "category": "military",
        "name": "Active Conflict Zones", "description": "Regions with ongoing armed conflict",
        "icon": "⚔️", "color": "#ff2200", "live": False,
    },
    "military_bases": {
        "id": "military_bases", "category": "military",
        "name": "Military Bases", "description": "Known military installation locations",
        "icon": "🪖", "color": "#8b4513", "live": False,
    },
    "naval_activity": {
        "id": "naval_activity", "category": "military",
        "name": "Naval Activity", "description": "Major naval vessel positions",
        "icon": "⚓", "color": "#003580", "live": False,
    },
    "arms_trade": {
        "id": "arms_trade", "category": "military",
        "name": "Arms Trade Routes", "description": "Major arms export/import flows",
        "icon": "🔫", "color": "#556b2f", "live": False,
    },
    # ---- Disasters / Environment ----
    "earthquakes": {
        "id": "earthquakes", "category": "disasters",
        "name": "Seismic Activity", "description": "Recent earthquakes M4.0+",
        "icon": "🌋", "color": "#ff6600", "live": False,
    },
    "wildfires": {
        "id": "wildfires", "category": "disasters",
        "name": "Wildfires", "description": "Active wildfire perimeters",
        "icon": "🔥", "color": "#ff4500", "live": False,
    },
    "hurricanes": {
        "id": "hurricanes", "category": "disasters",
        "name": "Tropical Storms", "description": "Active tropical storm tracks",
        "icon": "🌀", "color": "#00bfff", "live": False,
    },
    "floods": {
        "id": "floods", "category": "disasters",
        "name": "Flood Alerts", "description": "Active flood-warning regions",
        "icon": "🌊", "color": "#1e90ff", "live": False,
    },
    "oil_spills": {
        "id": "oil_spills", "category": "disasters",
        "name": "Oil Spills", "description": "Reported marine oil spills",
        "icon": "🛢️", "color": "#8b0000", "live": False,
    },
    "droughts": {
        "id": "droughts", "category": "disasters",
        "name": "Drought Severity", "description": "Multi-year drought index",
        "icon": "🏜️", "color": "#daa520", "live": False,
    },
    # ---- Financial ----
    "market_volatility": {
        "id": "market_volatility", "category": "financial",
        "name": "Market Volatility", "description": "Stock market VIX by country",
        "icon": "📈", "color": "#00ff88", "live": True,
    },
    "currency_stress": {
        "id": "currency_stress", "category": "financial",
        "name": "Currency Stress", "description": "Currency depreciation vs USD",
        "icon": "💱", "color": "#ffd700", "live": True,
    },
    "gdp_growth": {
        "id": "gdp_growth", "category": "financial",
        "name": "GDP Growth Rate", "description": "Annual GDP growth by country",
        "icon": "💹", "color": "#00e676", "live": False,
    },
    "inflation": {
        "id": "inflation", "category": "financial",
        "name": "Inflation Rate", "description": "Annual inflation by country",
        "icon": "💸", "color": "#ff9800", "live": False,
    },
    "trade_routes": {
        "id": "trade_routes", "category": "financial",
        "name": "Trade Routes", "description": "Major maritime trade lanes",
        "icon": "🚢", "color": "#40c4ff", "live": False,
    },
    "sanctions": {
        "id": "sanctions", "category": "financial",
        "name": "Sanctions Tracker", "description": "Active OFAC/EU sanctions",
        "icon": "🚫", "color": "#f44336", "live": False,
    },
    # ---- Infrastructure ----
    "data_centers": {
        "id": "data_centers", "category": "infrastructure",
        "name": "Data Centers", "description": "Major hyperscale data center locations",
        "icon": "🖥️", "color": "#00bcd4", "live": False,
    },
    "submarine_cables": {
        "id": "submarine_cables", "category": "infrastructure",
        "name": "Submarine Cables", "description": "International undersea cable routes",
        "icon": "🔌", "color": "#4caf50", "live": False,
    },
    "power_grid": {
        "id": "power_grid", "category": "infrastructure",
        "name": "Power Grid Stress", "description": "Electrical grid vulnerability index",
        "icon": "⚡", "color": "#ffeb3b", "live": False,
    },
    "nuclear_facilities": {
        "id": "nuclear_facilities", "category": "infrastructure",
        "name": "Nuclear Facilities", "description": "Civil nuclear power plant locations",
        "icon": "☢️", "color": "#76ff03", "live": False,
    },
    "oil_gas_pipelines": {
        "id": "oil_gas_pipelines", "category": "infrastructure",
        "name": "Oil & Gas Pipelines", "description": "Major energy pipeline routes",
        "icon": "🛢️", "color": "#795548", "live": False,
    },
    "satellite_coverage": {
        "id": "satellite_coverage", "category": "infrastructure",
        "name": "Satellite Coverage", "description": "LEO satellite internet footprint",
        "icon": "🛰️", "color": "#ab47bc", "live": False,
    },
    "5g_coverage": {
        "id": "5g_coverage", "category": "infrastructure",
        "name": "5G Coverage", "description": "5G network deployment density",
        "icon": "📡", "color": "#26c6da", "live": False,
    },
    # ---- Geopolitical ----
    "country_risk": {
        "id": "country_risk", "category": "geopolitical",
        "name": "Country Risk Score", "description": "Composite geopolitical risk choropleth",
        "icon": "🌡️", "color": "#ef5350", "live": True,
    },
    "political_stability": {
        "id": "political_stability", "category": "geopolitical",
        "name": "Political Stability", "description": "World Bank political stability index",
        "icon": "🏛️", "color": "#42a5f5", "live": False,
    },
    "protest_activity": {
        "id": "protest_activity", "category": "geopolitical",
        "name": "Social Unrest", "description": "Active protest and civil unrest events",
        "icon": "✊", "color": "#ff7043", "live": False,
    },
    "border_tensions": {
        "id": "border_tensions", "category": "geopolitical",
        "name": "Border Tensions", "description": "Active cross-border disputes",
        "icon": "🗺️", "color": "#ff5722", "live": False,
    },
    "terrorism_incidents": {
        "id": "terrorism_incidents", "category": "geopolitical",
        "name": "Terrorism Incidents", "description": "Recent GTD-tracked incidents",
        "icon": "💥", "color": "#b71c1c", "live": False,
    },
    "press_freedom": {
        "id": "press_freedom", "category": "geopolitical",
        "name": "Press Freedom Index", "description": "RSF World Press Freedom Index",
        "icon": "📰", "color": "#80cbc4", "live": False,
    },
    "corruption_index": {
        "id": "corruption_index", "category": "geopolitical",
        "name": "Corruption Index", "description": "Transparency International CPI",
        "icon": "💰", "color": "#ffa726", "live": False,
    },
    "internet_censorship": {
        "id": "internet_censorship", "category": "geopolitical",
        "name": "Internet Censorship", "description": "Freedom House internet freedom score",
        "icon": "🔒", "color": "#e53935", "live": False,
    },
    # ---- Health / Humanitarian ----
    "disease_outbreaks": {
        "id": "disease_outbreaks", "category": "health",
        "name": "Disease Outbreaks", "description": "WHO ProMED outbreak alerts",
        "icon": "🦠", "color": "#ce93d8", "live": False,
    },
    "refugee_flows": {
        "id": "refugee_flows", "category": "health",
        "name": "Refugee Flows", "description": "UNHCR major displacement corridors",
        "icon": "🧳", "color": "#ffcc02", "live": False,
    },
    "food_insecurity": {
        "id": "food_insecurity", "category": "health",
        "name": "Food Insecurity", "description": "IPC Phase 3+ food crisis zones",
        "icon": "🌾", "color": "#ff8f00", "live": False,
    },
    "water_stress": {
        "id": "water_stress", "category": "health",
        "name": "Water Stress", "description": "Aqueduct Water Risk Atlas index",
        "icon": "💧", "color": "#039be5", "live": False,
    },
    # ---- Space / Environment ----
    "space_weather": {
        "id": "space_weather", "category": "environment",
        "name": "Space Weather", "description": "NOAA GOES solar activity alerts",
        "icon": "☀️", "color": "#ffee58", "live": False,
    },
    "air_quality": {
        "id": "air_quality", "category": "environment",
        "name": "Air Quality Index", "description": "Global PM2.5 real-time AQI",
        "icon": "💨", "color": "#80cbc4", "live": False,
    },
    "co2_emissions": {
        "id": "co2_emissions", "category": "environment",
        "name": "CO₂ Emissions", "description": "Country-level CO₂ emissions (Gt)",
        "icon": "🌫️", "color": "#90a4ae", "live": False,
    },
    "piracy": {
        "id": "piracy", "category": "maritime",
        "name": "Piracy Incidents", "description": "IMB maritime piracy incident reports",
        "icon": "🏴‍☠️", "color": "#37474f", "live": False,
    },
    "drug_trafficking": {
        "id": "drug_trafficking", "category": "geopolitical",
        "name": "Drug Trafficking Routes", "description": "UNODC major drug trafficking corridors",
        "icon": "💊", "color": "#880e4f", "live": False,
    },
    # ---- Transport (real data) ----
    "flight_tracking": {
        "id": "flight_tracking", "category": "transport",
        "name": "Live Flight Tracking", "description": "Real-time aircraft positions (OpenSky Network)",
        "icon": "✈️", "color": "#29b6f6", "live": True,
    },
    # ---- Maritime (real data) ----
    "vessel_tracking": {
        "id": "vessel_tracking", "category": "maritime",
        "name": "Live Vessel Tracking", "description": "AIS vessel positions (AISHub / simulation fallback)",
        "icon": "🚢", "color": "#0077b6", "live": True,
    },
    # ---- Natural Disasters (GDACS real data) ----
    "gdacs_disasters": {
        "id": "gdacs_disasters", "category": "disasters",
        "name": "GDACS Disasters", "description": "Floods, cyclones & volcanoes (GDACS RSS feed)",
        "icon": "🌊", "color": "#ff6b35", "live": True,
    },
    # ---- Weather (real data) ----
    "weather": {
        "id": "weather", "category": "environment",
        "name": "Live Weather", "description": "Current conditions for major cities (Open-Meteo)",
        "icon": "🌦️", "color": "#4fc3f7", "live": True,
    },
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LayerDefinition(BaseModel):
    id: str
    category: str
    name: str
    description: str
    icon: str
    color: str
    live: bool


class LayerFeature(BaseModel):
    id: str
    type: str = "Feature"
    lat: float
    lng: float
    value: float
    label: str
    extra: dict = {}  # type: ignore[assignment]


class LayerDataResponse(BaseModel):
    layer_id: str
    features: List[LayerFeature]
    last_updated: float
    count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[LayerDefinition],
    tags=["layers"],
    summary="List all available data layers",
)
async def list_layers(category: Optional[str] = Query(default=None)):
    layers = list(LAYER_REGISTRY.values())
    if category:
        layers = [lay for lay in layers if lay["category"] == category]
    return [LayerDefinition(**lay) for lay in layers]


@router.get(
    "/categories",
    tags=["layers"],
    summary="List layer categories",
)
async def list_categories():
    cats = sorted({lay["category"] for lay in LAYER_REGISTRY.values()})
    return {"categories": cats}


@router.get(
    "/{layer_id}",
    response_model=LayerDataResponse,
    tags=["layers"],
    summary="Get data for a specific layer",
)
async def get_layer_data(
    layer_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
):
    if layer_id not in LAYER_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Layer '{layer_id}' not found")

    features = await _generate_layer_data(layer_id, limit)
    return LayerDataResponse(
        layer_id=layer_id,
        features=features,
        last_updated=time.time(),
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Data generators for each layer type
# ---------------------------------------------------------------------------

async def _generate_layer_data(layer_id: str, limit: int) -> List[LayerFeature]:
    """Route layer_id to its data generator."""
    generators = {
        "cyber_attacks": _cyber_attacks_data,
        "conflict_zones": _conflict_zones_data,
        "military_bases": _military_bases_data,
        "earthquakes": _earthquakes_data,
        "wildfires": _wildfires_data,
        "nuclear_facilities": _nuclear_facilities_data,
        "data_centers": _data_centers_data,
        "country_risk": _country_risk_data,
        "disease_outbreaks": _disease_outbreaks_data,
        "terrorist_incidents": _terrorist_incidents_data,
        "piracy": _piracy_data,
        "submarine_cables": _submarine_cables_data,
        "flight_tracking": _flight_tracking_data,
        "weather": _weather_data,
        "gdacs_disasters": _gdacs_disasters_data,
        "vessel_tracking": _vessel_tracking_data,
    }

    gen = generators.get(layer_id)
    if gen:
        return await gen(limit)
    # Default: simulated point data
    return _random_points(layer_id, limit // 5)


async def _cyber_attacks_data(limit: int) -> List[LayerFeature]:
    """Live cyber attack data from the in-memory buffer."""
    from app.main import processor

    features = []
    if processor:
        events = processor.get_recent_events(limit)
        for ev in events:
            features.append(LayerFeature(
                id=ev.get("id", ""),
                lat=ev.get("dest_lat", 0),
                lng=ev.get("dest_lng", 0),
                value=ev.get("severity", 5) / 10,
                label=f"{ev.get('attack_type', '?')} → {ev.get('dest_country', '?')}",
                extra={"attack_type": ev.get("attack_type"), "severity": ev.get("severity")},
            ))
    return features


# Static data for military/infrastructure layers (sourced from public knowledge)
_CONFLICT_ZONES = [
    (33.9, 67.7, "Afghanistan", 0.95),
    (15.5, 48.5, "Yemen", 0.92),
    (34.8, 38.8, "Syria", 0.90),
    (48.4, 31.2, "Ukraine (East)", 0.88),
    (12.8, 30.2, "Sudan", 0.85),
    (7.9, 30.2, "South Sudan", 0.82),
    (9.5, 44.5, "Somalia", 0.88),
    (6.6, 20.9, "CAR", 0.80),
    (17.6, -4.0, "Mali", 0.78),
    (31.5, 35.1, "Gaza", 0.95),
    (13.5, 2.1, "Niger", 0.72),
    (12.3, 13.4, "Nigeria (NE)", 0.75),
    (-4.0, 21.7, "DR Congo (East)", 0.82),
]

async def _conflict_zones_data(limit: int) -> List[LayerFeature]:
    return [
        LayerFeature(id=f"conflict_{i}", lat=lat, lng=lng, value=val, label=name)
        for i, (lat, lng, name, val) in enumerate(_CONFLICT_ZONES)
    ]

_MILITARY_BASES = [
    (36.8, -76.3, "Norfolk Naval Station, USA", "US Navy"),
    (28.5, -80.6, "Cape Canaveral SFS, USA", "USSF"),
    (51.9, 1.3, "RAF Mildenhall, UK", "USAF/RAF"),
    (49.7, 8.6, "Ramstein AB, Germany", "USAF"),
    (26.4, 127.8, "Kadena AB, Japan", "USAF"),
    (35.5, 139.8, "Yokota AB, Japan", "USAF"),
    (1.3, 103.8, "Changi Air Base, Singapore", "RSAF"),
    (-12.2, 96.8, "Diego Garcia, BIOT", "US/UK"),
    (36.1, 36.2, "İncirlik AB, Turkey", "USAF/TAF"),
    (26.1, 50.6, "NSA Bahrain", "US Navy"),
    (25.3, 55.4, "Al Dhafra AB, UAE", "USAF"),
    (-17.7, 177.4, "RFMF Base Suva, Fiji", "RFMF"),
    (55.7, 37.6, "Kubinka AB, Russia", "Russian AF"),
    (23.6, 58.3, "Muscat Royal AF, Oman", "RAFO"),
]

async def _military_bases_data(limit: int) -> List[LayerFeature]:
    return [
        LayerFeature(id=f"base_{i}", lat=lat, lng=lng, value=0.8, label=name,
                     extra={"operator": op})
        for i, (lat, lng, name, op) in enumerate(_MILITARY_BASES[:limit])
    ]


async def _earthquakes_data(limit: int) -> List[LayerFeature]:
    """Real earthquake data from USGS GeoJSON feed (free, no key required)."""
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                features: List[LayerFeature] = []
                for feat in data.get("features", [])[:limit]:
                    props = feat.get("properties", {})
                    coords = feat.get("geometry", {}).get("coordinates", [0, 0, 0])
                    mag = props.get("mag", 0) or 0
                    place = props.get("place", "Unknown") or "Unknown"
                    features.append(LayerFeature(
                        id=feat.get("id", f"eq_{len(features)}"),
                        lat=round(coords[1], 4),
                        lng=round(coords[0], 4),
                        value=round(max(0.0, min(1.0, (mag - 2.5) / 5.5)), 2),
                        label=f"M{mag:.1f} – {place}",
                        extra={
                            "magnitude": round(mag, 1),
                            "depth_km": round(coords[2], 1) if len(coords) > 2 else None,
                            "time": props.get("time"),
                            "url": props.get("url", ""),
                            "is_real": True,
                        },
                    ))
                return features
    except Exception as exc:
        logger.debug("USGS earthquake fetch failed: %s", exc)
    # Fallback: simulated data
    belt = [
        (35.0, 137.0), (-6.0, 105.0), (40.0, 142.0), (-15.0, -75.0),
        (38.0, 30.0), (28.0, 84.0), (4.0, 97.0), (-40.0, 174.0),
        (36.0, -118.0), (19.5, -155.5), (15.0, -90.0), (-33.0, -71.0),
        (60.0, -153.0), (5.0, 125.0),
    ]
    fallback = []
    for i in range(min(limit, 40)):
        base_lat, base_lng = belt[i % len(belt)]
        lat = base_lat + random.gauss(0, 3)
        lng = base_lng + random.gauss(0, 3)
        magnitude = random.uniform(2.5, 7.5)
        fallback.append(LayerFeature(
            id=f"eq_sim_{i}", lat=round(lat, 2), lng=round(lng, 2),
            value=round((magnitude - 2.5) / 5.5, 2),
            label=f"M{magnitude:.1f} (simulated)",
            extra={"magnitude": round(magnitude, 1), "is_real": False},
        ))
    return fallback


async def _wildfires_data(limit: int) -> List[LayerFeature]:
    hotspots = [
        (38.5, -121.0, "California"), (-33.0, 151.0, "NSW Australia"),
        (55.0, -100.0, "Canadian Boreal"), (-15.0, -55.0, "Amazon"),
        (60.0, 90.0, "Siberia"), (36.0, 28.0, "Mediterranean"),
        (-34.0, 22.0, "South Africa"), (51.5, 36.5, "Ukraine"),
    ]
    return [
        LayerFeature(
            id=f"fire_{i}", lat=lat + random.gauss(0, 1), lng=lng + random.gauss(0, 1),
            value=random.uniform(0.4, 1.0), label=f"Wildfire near {name}",
            extra={"area_ha": random.randint(100, 50000)},
        )
        for i, (lat, lng, name) in enumerate(hotspots)
    ]


async def _nuclear_facilities_data(limit: int) -> List[LayerFeature]:
    plants = [
        (35.5, 135.9, "Mihama, Japan", "PWR"), (41.6, -87.5, "Braidwood, USA", "PWR"),
        (49.5, 0.8, "Paluel, France", "PWR"), (53.8, -1.6, "Sellafield, UK", "GCR"),
        (56.8, 60.6, "Beloyarsk, Russia", "BN-800"), (23.9, 120.6, "Chinshan, Taiwan", "BWR"),
        (35.4, 129.3, "Kori, South Korea", "PWR"), (22.8, 72.6, "Kakrapar, India", "PHWR"),
        (40.4, 17.9, "Brindisi, Italy", "—"), (52.4, 4.6, "Borssele, Netherlands", "PWR"),
        (50.7, 7.2, "Grafenrheinfeld, Germany", "PWR"), (54.5, 26.1, "Ostrovets, Belarus", "VVER"),
        (46.5, 30.1, "South Ukraine NPP", "VVER"), (48.4, 34.6, "Zaporizhzhia, Ukraine", "VVER"),
        (34.7, 48.5, "Bushehr, Iran", "VVER"), (27.4, 30.4, "El Dabaa, Egypt", "VVER"),
    ]
    return [
        LayerFeature(id=f"nuke_{i}", lat=lat, lng=lng, value=0.5,
                     label=name, extra={"type": reactor})
        for i, (lat, lng, name, reactor) in enumerate(plants[:limit])
    ]


async def _data_centers_data(limit: int) -> List[LayerFeature]:
    dcs = [
        (47.6, -122.3, "Azure West US", "Microsoft"), (37.4, -122.1, "GCP us-west1", "Google"),
        (39.0, -77.4, "AWS us-east-1", "Amazon"), (53.3, -6.3, "Azure North Europe", "Microsoft"),
        (59.9, 10.8, "Azure Norway East", "Microsoft"), (22.3, 114.2, "GCP asia-east2", "Google"),
        (35.7, 139.7, "AWS ap-northeast-1", "Amazon"), (-33.9, 151.2, "AWS ap-southeast-2", "Amazon"),
        (1.4, 103.8, "GCP asia-southeast1", "Google"), (50.1, 8.7, "GCP europe-west3", "Google"),
        (19.1, 72.9, "Azure India West", "Microsoft"), (-23.5, -46.6, "AWS sa-east-1", "Amazon"),
        (55.9, 37.6, "Yandex Cloud Moscow", "Yandex"), (39.9, 116.4, "Alibaba cn-beijing", "Alibaba"),
        (31.2, 121.5, "Tencent ap-shanghai", "Tencent"),
    ]
    return [
        LayerFeature(id=f"dc_{i}", lat=lat, lng=lng, value=0.8,
                     label=name, extra={"provider": provider})
        for i, (lat, lng, name, provider) in enumerate(dcs[:limit])
    ]


async def _country_risk_data(limit: int) -> List[LayerFeature]:
    from app.services.country_risk import country_risk_service

    scores = await country_risk_service.get_all_scores()
    return [
        LayerFeature(
            id=s.iso2, lat=s.lat, lng=s.lng,
            value=round(s.risk_score / 100, 2),
            label=f"{s.name}: {s.risk_score:.0f}",
            extra={"iso2": s.iso2, "iso3": s.iso3, "cyber": s.cyber_score, "news": s.news_score},
        )
        for s in scores[:limit]
    ]


async def _disease_outbreaks_data(limit: int) -> List[LayerFeature]:
    outbreaks = [
        (12.0, 17.0, "Cholera – Chad", 0.7),
        (-1.3, 36.8, "Mpox – DRC/East Africa", 0.85),
        (23.6, 90.4, "Dengue – Bangladesh", 0.6),
        (12.9, 77.6, "Nipah – India", 0.9),
        (10.5, 7.4, "Yellow Fever – Nigeria", 0.65),
        (14.5, 46.5, "Cholera – Yemen", 0.80),
        (-8.9, 13.2, "Marburg – Angola", 0.95),
        (3.9, 11.5, "Mpox – Cameroon", 0.70),
        (15.6, 32.5, "Dengue – Sudan", 0.60),
    ]
    return [
        LayerFeature(id=f"dis_{i}", lat=lat, lng=lng, value=val, label=name)
        for i, (lat, lng, name, val) in enumerate(outbreaks[:limit])
    ]


async def _terrorist_incidents_data(limit: int) -> List[LayerFeature]:
    return _random_points("terrorism", min(limit, 30), lat_range=(-15, 40), lng_range=(-20, 80))


async def _piracy_data(limit: int) -> List[LayerFeature]:
    # IMB piracy hotspots
    hotspots = [
        (4.0, 51.5, "Gulf of Aden"), (1.2, 104.5, "Singapore Strait"),
        (11.0, 43.0, "Gulf of Aden"), (5.0, 2.0, "Gulf of Guinea"),
        (-8.0, 39.0, "Mozambique Channel"), (12.0, 115.0, "South China Sea"),
        (24.0, 59.0, "Gulf of Oman"), (-5.0, 105.0, "Java Sea"),
    ]
    features = []
    for i, (lat, lng, name) in enumerate(hotspots):
        for j in range(random.randint(1, 4)):
            features.append(LayerFeature(
                id=f"piracy_{i}_{j}",
                lat=lat + random.gauss(0, 0.5),
                lng=lng + random.gauss(0, 0.5),
                value=random.uniform(0.3, 0.9),
                label=f"Piracy incident – {name}",
            ))
    return features[:limit]


async def _submarine_cables_data(limit: int) -> List[LayerFeature]:
    """Key submarine cable landing points."""
    landing_points = [
        (51.4, 1.0, "Channel Crossing", "SEACOM"), (37.8, -122.4, "Pacific Gateway", "Google"),
        (35.7, 139.8, "Japan Gateway", "NEC"), (1.3, 103.8, "Singapore Hub", "Multi"),
        (-33.9, 18.4, "Cape Town", "SEACOM"), (19.4, 72.8, "Mumbai Hub", "Multi"),
        (25.2, 55.3, "Dubai Hub", "Multi"), (30.1, 31.3, "Alexandria Hub", "Multi"),
        (-23.0, -43.2, "Rio de Janeiro", "EllaLink"), (34.0, -118.4, "Los Angeles", "PLCN"),
        (40.7, -74.0, "New York Hub", "Multi"), (48.9, 2.4, "Paris Hub", "Multi"),
    ]
    return [
        LayerFeature(id=f"cable_{i}", lat=lat, lng=lng, value=0.9,
                     label=f"{name} ({cable})")
        for i, (lat, lng, name, cable) in enumerate(landing_points[:limit])
    ]


def _random_points(
    layer_id: str,
    count: int,
    lat_range: tuple = (-60, 75),
    lng_range: tuple = (-180, 180),
) -> List[LayerFeature]:
    """Generate random plausible point data for unsupported layers."""
    rng = random.Random(hash(layer_id) % 2**32)
    return [
        LayerFeature(
            id=f"{layer_id}_{i}",
            lat=round(rng.uniform(*lat_range), 2),
            lng=round(rng.uniform(*lng_range), 2),
            value=round(rng.uniform(0.1, 1.0), 2),
            label=layer_id.replace("_", " ").title(),
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Real-data layer handlers: OpenSky (flights) + Open-Meteo (weather)
# ---------------------------------------------------------------------------

async def _flight_tracking_data(limit: int) -> List[LayerFeature]:
    """Live flight positions from OpenSky Network (anonymous, free tier)."""
    # Limit to a bounding box to keep response size manageable
    url = "https://opensky-network.org/api/states/all?lamin=-60&lomin=-180&lamax=75&lomax=180"
    try:
        import httpx as _httpx
        # OpenSky allows ~100 anonymous requests/day; use a short timeout
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "GlobalIntelDashboard/2.0"})
            if resp.status_code == 200:
                data = resp.json()
                states = data.get("states") or []
                features: List[LayerFeature] = []
                for state in states[:limit]:
                    # OpenSky state vector: [icao24, callsign, origin_country,
                    #   time_pos, last_contact, longitude, latitude, baro_altitude,
                    #   on_ground, velocity, heading, vertical_rate, ...]
                    if not state or len(state) < 9:
                        continue
                    lng = state[5]
                    lat = state[6]
                    if lat is None or lng is None:
                        continue
                    callsign = (state[1] or "").strip() or state[0]
                    country = state[2] or "?"
                    altitude = state[7] or 0
                    velocity = state[9] or 0
                    on_ground = state[8]
                    if on_ground:
                        continue
                    features.append(LayerFeature(
                        id=state[0],
                        lat=round(lat, 4),
                        lng=round(lng, 4),
                        value=min(1.0, (altitude or 0) / 12000),
                        label=f"✈ {callsign} ({country})",
                        extra={
                            "callsign": callsign,
                            "country": country,
                            "altitude_m": round(altitude, 0),
                            "velocity_ms": round(velocity, 1),
                            "is_real": True,
                        },
                    ))
                return features
    except Exception as exc:
        logger.debug("OpenSky fetch failed: %s", exc)
    # Fallback
    return _random_points("flights", min(limit, 50))


# Major city lat/lng for weather sampling
_WEATHER_CITIES = [
    (40.7, -74.0, "New York"), (51.5, -0.1, "London"), (48.9, 2.3, "Paris"),
    (52.5, 13.4, "Berlin"), (35.7, 139.7, "Tokyo"), (39.9, 116.4, "Beijing"),
    (28.6, 77.2, "New Delhi"), (-23.5, -46.6, "São Paulo"), (55.8, 37.6, "Moscow"),
    (-33.9, 18.4, "Cape Town"), (1.3, 103.8, "Singapore"), (25.2, 55.3, "Dubai"),
    (37.6, -122.4, "San Francisco"), (-37.8, 144.9, "Melbourne"), (19.4, -99.1, "Mexico City"),
    (41.0, 28.9, "Istanbul"), (31.0, 35.2, "Tel Aviv"), (24.7, 46.7, "Riyadh"),
]


async def _weather_data(limit: int) -> List[LayerFeature]:
    """Live weather data from Open-Meteo (free, no key required)."""
    cities = _WEATHER_CITIES[:min(limit, len(_WEATHER_CITIES))]
    lat_str = ",".join(str(c[0]) for c in cities)
    lng_str = ",".join(str(c[1]) for c in cities)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat_str}&longitude={lng_str}"
        "&current=temperature_2m,weather_code,wind_speed_10m"
        "&timezone=UTC&forecast_days=1"
    )
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                # When multiple locations are requested, response is a list
                results = data if isinstance(data, list) else [data]
                features: List[LayerFeature] = []
                for i, city in enumerate(cities):
                    if i >= len(results):
                        break
                    res = results[i]
                    cur = res.get("current", {})
                    temp = cur.get("temperature_2m")
                    wind = cur.get("wind_speed_10m", 0)
                    wcode = cur.get("weather_code", 0)
                    if temp is None:
                        continue
                    # Normalize temp to 0–1 (-30°C → 50°C range)
                    norm = max(0.0, min(1.0, (temp + 30) / 80))
                    icon = _wmo_icon(wcode)
                    features.append(LayerFeature(
                        id=f"wx_{i}",
                        lat=city[0],
                        lng=city[1],
                        value=round(norm, 2),
                        label=f"{icon} {city[2]}: {temp}°C",
                        extra={
                            "city": city[2],
                            "temperature_c": temp,
                            "wind_kmh": wind,
                            "weather_code": wcode,
                            "is_real": True,
                        },
                    ))
                return features
    except Exception as exc:
        logger.debug("Open-Meteo fetch failed: %s", exc)
    return _random_points("weather", min(limit, 20))


def _wmo_icon(code: int) -> str:
    """Map WMO weather code to an emoji icon."""
    if code == 0:
        return "☀️"
    if code in (1, 2, 3):
        return "⛅"
    if code in (45, 48):
        return "🌫️"
    if code in range(51, 68):
        return "🌧️"
    if code in range(71, 78):
        return "❄️"
    if code in range(80, 83):
        return "🌦️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌡️"


# ---------------------------------------------------------------------------
# GDACS natural disaster feed (real data)
# ---------------------------------------------------------------------------

async def _gdacs_disasters_data(limit: int) -> List[LayerFeature]:
    """Live disaster events from the GDACS RSS feed (free, no key required).

    GDACS covers floods (FL), cyclones (TC), earthquakes (EQ), volcanoes (VO),
    droughts (DR), and wildfires (WF).
    """
    url = "https://www.gdacs.org/xml/rss.xml"
    alert_colors = {"Red": 1.0, "Orange": 0.65, "Green": 0.35}
    event_icons = {
        "EQ": "🌋", "TC": "🌀", "FL": "🌊", "VO": "🌋",
        "DR": "🏜️", "WF": "🔥",
    }
    try:
        import xml.etree.ElementTree as ET

        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "GlobalIntelDashboard/2.0"},
            )
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {
                    "gdacs": "http://www.gdacs.org",
                    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
                }
                features: List[LayerFeature] = []
                channel = root.find("channel")
                items = channel.findall("item") if channel is not None else root.findall(".//item")
                for idx, item in enumerate(items[:limit]):
                    title = (item.findtext("title") or "").strip()
                    event_type = (
                        item.findtext("gdacs:eventtype", namespaces=ns) or ""
                    ).upper()
                    alert_level = (
                        item.findtext("gdacs:alertlevel", namespaces=ns) or "Green"
                    )
                    lat_text = item.findtext("geo:lat", namespaces=ns)
                    lng_text = item.findtext("geo:long", namespaces=ns)
                    if lat_text is None or lng_text is None:
                        continue
                    try:
                        lat = float(lat_text)
                        lng = float(lng_text)
                    except ValueError:
                        continue
                    icon = event_icons.get(event_type, "⚠️")
                    value = alert_colors.get(alert_level, 0.3)
                    features.append(LayerFeature(
                        id=f"gdacs_{idx}",
                        lat=round(lat, 4),
                        lng=round(lng, 4),
                        value=value,
                        label=f"{icon} {title}",
                        extra={
                            "event_type": event_type,
                            "alert_level": alert_level,
                            "is_real": True,
                        },
                    ))
                return features
    except Exception as exc:
        logger.debug("GDACS RSS fetch failed: %s", exc)

    # Fallback – simulated disaster events
    fallback_events = [
        (13.4, -16.6, "Flood – West Africa", "FL", 0.7),
        (-8.3, 115.2, "Volcano – Bali", "VO", 0.8),
        (14.1, 42.6, "Cyclone – Gulf of Aden", "TC", 0.9),
        (20.5, 121.0, "Typhoon – Philippines", "TC", 0.85),
        (-1.3, 36.8, "Flood – East Africa", "FL", 0.6),
        (28.5, 84.1, "Earthquake – Nepal", "EQ", 0.75),
        (51.5, 10.5, "Wildfire – Central Europe", "WF", 0.4),
    ]
    icons_map = {"FL": "🌊", "VO": "🌋", "TC": "🌀", "EQ": "🌋", "WF": "🔥"}
    return [
        LayerFeature(
            id=f"gdacs_sim_{i}",
            lat=round(lat + random.gauss(0, 0.5), 3),
            lng=round(lng + random.gauss(0, 0.5), 3),
            value=val,
            label=f"{icons_map.get(etype, '⚠️')} {name} (simulated)",
            extra={"event_type": etype, "alert_level": "Orange", "is_real": False},
        )
        for i, (lat, lng, name, etype, val) in enumerate(fallback_events[:limit])
    ]


# ---------------------------------------------------------------------------
# Maritime AIS vessel tracking (real data with simulation fallback)
# ---------------------------------------------------------------------------

# Known major shipping lanes / ports for a realistic fallback
_SHIPPING_LANES = [
    (1.3, 103.8, "Singapore Strait"),
    (31.3, 32.3, "Suez Canal"),
    (29.9, -79.7, "US East Coast"),
    (35.7, 139.8, "Tokyo Bay"),
    (22.3, 114.2, "Hong Kong"),
    (51.9, 4.5, "Rotterdam"),
    (-33.9, 18.4, "Cape of Good Hope"),
    (37.9, -122.4, "San Francisco Bay"),
    (53.5, -0.1, "Humber Estuary"),
    (55.6, 12.6, "Øresund Strait"),
    (4.0, -51.5, "Atlantic Crossing"),
    (-23.0, -43.2, "Rio de Janeiro"),
    (30.1, 31.3, "Alexandria"),
    (25.2, 55.3, "Dubai/Jebel Ali"),
]

async def _vessel_tracking_data(limit: int) -> List[LayerFeature]:
    """Live AIS vessel positions.

    Attempts to use AISHub aggregate feed (free, public).
    Falls back to simulated shipping lane traffic if unavailable.
    """
    url = "https://www.aishub.net/api/2/data?format=2&output=json&compress=0"
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "GlobalIntelDashboard/2.0"},
            )
            if resp.status_code == 200:
                payload = resp.json()
                # AISHub returns a list of vessel dicts or {"ERROR": ...}
                vessels = payload if isinstance(payload, list) else payload.get("vessels", [])
                if not vessels:
                    raise ValueError("empty AIS response")
                features: List[LayerFeature] = []
                for vessel in vessels[:limit]:
                    lat = vessel.get("LATITUDE") or vessel.get("lat")
                    lng = vessel.get("LONGITUDE") or vessel.get("lon")
                    if lat is None or lng is None:
                        continue
                    name = (
                        vessel.get("NAME")
                        or vessel.get("name")
                        or vessel.get("MMSI", "")
                    )
                    sog = float(vessel.get("SOG") or vessel.get("speed") or 0)
                    features.append(LayerFeature(
                        id=str(vessel.get("MMSI", f"v_{len(features)}")),
                        lat=round(float(lat), 4),
                        lng=round(float(lng), 4),
                        value=min(1.0, sog / 25),
                        label=f"🚢 {name}",
                        extra={
                            "speed_kn": round(sog, 1),
                            "is_real": True,
                        },
                    ))
                if features:
                    return features
    except Exception as exc:
        logger.debug("AISHub fetch failed: %s", exc)

    # Simulated vessel traffic along major shipping lanes
    vessels = []
    rng = random.Random(int(time.time() / 300))  # change every 5 min
    for i in range(min(limit, 80)):
        lane = _SHIPPING_LANES[i % len(_SHIPPING_LANES)]
        lat = lane[0] + rng.gauss(0, 1.5)
        lng = lane[1] + rng.gauss(0, 2.0)
        speed = rng.uniform(5, 22)
        vessel_types = ["Tanker", "Container", "Bulk Carrier", "LNG", "RORO"]
        vessels.append(LayerFeature(
            id=f"vessel_sim_{i}",
            lat=round(lat, 3),
            lng=round(lng, 3),
            value=round(speed / 25, 2),
            label=f"🚢 {vessel_types[i % len(vessel_types)]} near {lane[2]}",
            extra={"speed_kn": round(speed, 1), "is_real": False},
        ))
    return vessels

