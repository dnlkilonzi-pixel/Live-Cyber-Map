"""Data layer REST API routes.

Serves data for the 40+ map overlay layers.  Many layers use simulated data
for demonstration; the architecture is designed to swap in live feeds later.
"""

from __future__ import annotations

import logging
import math
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
        layers = [l for l in layers if l["category"] == category]
    return [LayerDefinition(**l) for l in layers]


@router.get(
    "/categories",
    tags=["layers"],
    summary="List layer categories",
)
async def list_categories():
    cats = sorted({l["category"] for l in LAYER_REGISTRY.values()})
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
    """Simulated recent earthquakes (M4.0–8.0)."""
    # Major seismic belt coordinates
    belt = [
        (35.0, 137.0), (-6.0, 105.0), (40.0, 142.0), (-15.0, -75.0),
        (38.0, 30.0), (28.0, 84.0), (4.0, 97.0), (-40.0, 174.0),
        (36.0, -118.0), (19.5, -155.5), (15.0, -90.0), (-33.0, -71.0),
        (60.0, -153.0), (5.0, 125.0),
    ]
    features = []
    for i in range(min(limit, 40)):
        base_lat, base_lng = belt[i % len(belt)]
        lat = base_lat + random.gauss(0, 3)
        lng = base_lng + random.gauss(0, 3)
        magnitude = random.uniform(4.0, 7.5)
        features.append(LayerFeature(
            id=f"eq_{i}", lat=round(lat, 2), lng=round(lng, 2),
            value=round((magnitude - 4) / 4, 2),
            label=f"M{magnitude:.1f}",
            extra={"magnitude": round(magnitude, 1), "depth_km": random.randint(5, 200)},
        ))
    return features


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
