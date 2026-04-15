"""Country risk scoring service.

Aggregates multiple signals to produce a composite risk score (0–100) per country:
  - Cyber attack intensity (from the live attack stream)
  - News sentiment (from the news aggregator)
  - Static baseline factors (geopolitical stability, conflict, sanctions)

Higher score = higher risk.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CountryRisk:
    iso2: str                    # ISO 3166-1 alpha-2
    iso3: str                    # ISO 3166-1 alpha-3
    name: str
    risk_score: float            # 0–100 composite
    cyber_score: float           # 0–100
    news_score: float            # 0–100 (derived from sentiment)
    stability_baseline: float    # 0–100 static baseline
    attack_count_24h: int
    recent_events: List[str] = field(default_factory=list)
    lat: float = 0.0
    lng: float = 0.0
    last_updated: float = field(default_factory=time.time)


# Static baseline risk (higher = more risky) – geopolitical instability index
# Scale 0–100. Based on publicly available indices (Peace Index, Fragile States, etc.)
_BASELINE: Dict[str, Dict[str, float]] = {
    # format: iso2 -> {iso3, name, baseline, lat, lng}
    "AF": {"iso3": "AFG", "name": "Afghanistan", "baseline": 92, "lat": 33.9, "lng": 67.7},
    "SD": {"iso3": "SDN", "name": "Sudan", "baseline": 89, "lat": 12.8, "lng": 30.2},
    "SS": {"iso3": "SSD", "name": "South Sudan", "baseline": 91, "lat": 7.9, "lng": 30.2},
    "SY": {"iso3": "SYR", "name": "Syria", "baseline": 90, "lat": 34.8, "lng": 38.8},
    "YE": {"iso3": "YEM", "name": "Yemen", "baseline": 90, "lat": 15.5, "lng": 48.5},
    "SO": {"iso3": "SOM", "name": "Somalia", "baseline": 88, "lat": 5.2, "lng": 46.2},
    "CF": {"iso3": "CAF", "name": "Central African Rep.", "baseline": 85, "lat": 6.6, "lng": 20.9},
    "LY": {"iso3": "LBY", "name": "Libya", "baseline": 82, "lat": 26.3, "lng": 17.2},
    "ML": {"iso3": "MLI", "name": "Mali", "baseline": 80, "lat": 17.6, "lng": -4.0},
    "MM": {"iso3": "MMR", "name": "Myanmar", "baseline": 78, "lat": 21.9, "lng": 95.9},
    "RU": {"iso3": "RUS", "name": "Russia", "baseline": 72, "lat": 61.5, "lng": 105.3},
    "UA": {"iso3": "UKR", "name": "Ukraine", "baseline": 76, "lat": 48.4, "lng": 31.2},
    "IQ": {"iso3": "IRQ", "name": "Iraq", "baseline": 75, "lat": 33.2, "lng": 43.7},
    "IR": {"iso3": "IRN", "name": "Iran", "baseline": 72, "lat": 32.4, "lng": 53.7},
    "KP": {"iso3": "PRK", "name": "North Korea", "baseline": 80, "lat": 40.3, "lng": 127.5},
    "VE": {"iso3": "VEN", "name": "Venezuela", "baseline": 68, "lat": 6.4, "lng": -66.6},
    "CD": {"iso3": "COD", "name": "DR Congo", "baseline": 82, "lat": -4.0, "lng": 21.7},
    "NI": {"iso3": "NIC", "name": "Nicaragua", "baseline": 60, "lat": 12.9, "lng": -85.2},
    "HT": {"iso3": "HTI", "name": "Haiti", "baseline": 78, "lat": 18.9, "lng": -72.3},
    "BY": {"iso3": "BLR", "name": "Belarus", "baseline": 62, "lat": 53.7, "lng": 28.0},
    "CU": {"iso3": "CUB", "name": "Cuba", "baseline": 55, "lat": 21.5, "lng": -79.5},
    "PK": {"iso3": "PAK", "name": "Pakistan", "baseline": 68, "lat": 30.4, "lng": 69.3},
    "ET": {"iso3": "ETH", "name": "Ethiopia", "baseline": 72, "lat": 9.1, "lng": 40.5},
    "NG": {"iso3": "NGA", "name": "Nigeria", "baseline": 70, "lat": 9.1, "lng": 8.7},
    "MX": {"iso3": "MEX", "name": "Mexico", "baseline": 58, "lat": 23.6, "lng": -102.6},
    "BR": {"iso3": "BRA", "name": "Brazil", "baseline": 48, "lat": -14.2, "lng": -51.9},
    "CN": {"iso3": "CHN", "name": "China", "baseline": 38, "lat": 35.9, "lng": 104.2},
    "IN": {"iso3": "IND", "name": "India", "baseline": 42, "lat": 20.6, "lng": 78.9},
    "US": {"iso3": "USA", "name": "United States", "baseline": 30, "lat": 37.1, "lng": -95.7},
    "GB": {"iso3": "GBR", "name": "United Kingdom", "baseline": 22, "lat": 55.4, "lng": -3.4},
    "DE": {"iso3": "DEU", "name": "Germany", "baseline": 18, "lat": 51.2, "lng": 10.5},
    "FR": {"iso3": "FRA", "name": "France", "baseline": 22, "lat": 46.2, "lng": 2.2},
    "JP": {"iso3": "JPN", "name": "Japan", "baseline": 15, "lat": 36.2, "lng": 138.3},
    "AU": {"iso3": "AUS", "name": "Australia", "baseline": 12, "lat": -25.3, "lng": 133.8},
    "CA": {"iso3": "CAN", "name": "Canada", "baseline": 12, "lat": 56.1, "lng": -106.3},
    "NO": {"iso3": "NOR", "name": "Norway", "baseline": 8, "lat": 60.5, "lng": 8.5},
    "SE": {"iso3": "SWE", "name": "Sweden", "baseline": 9, "lat": 60.1, "lng": 18.6},
    "CH": {"iso3": "CHE", "name": "Switzerland", "baseline": 8, "lat": 46.8, "lng": 8.2},
    "NL": {"iso3": "NLD", "name": "Netherlands", "baseline": 12, "lat": 52.1, "lng": 5.3},
    "SG": {"iso3": "SGP", "name": "Singapore", "baseline": 10, "lat": 1.4, "lng": 103.8},
    "IL": {"iso3": "ISR", "name": "Israel", "baseline": 62, "lat": 31.0, "lng": 35.0},
    "PS": {"iso3": "PSE", "name": "Palestine", "baseline": 85, "lat": 31.9, "lng": 35.3},
    "SA": {"iso3": "SAU", "name": "Saudi Arabia", "baseline": 45, "lat": 23.9, "lng": 45.1},
    "TR": {"iso3": "TUR", "name": "Turkey", "baseline": 50, "lat": 38.9, "lng": 35.2},
    "EG": {"iso3": "EGY", "name": "Egypt", "baseline": 55, "lat": 26.8, "lng": 30.8},
    "ZA": {"iso3": "ZAF", "name": "South Africa", "baseline": 52, "lat": -30.6, "lng": 22.9},
    "KE": {"iso3": "KEN", "name": "Kenya", "baseline": 55, "lat": -0.0, "lng": 37.9},
    "TH": {"iso3": "THA", "name": "Thailand", "baseline": 42, "lat": 15.9, "lng": 100.9},
    "PH": {"iso3": "PHL", "name": "Philippines", "baseline": 52, "lat": 12.9, "lng": 121.8},
    "ID": {"iso3": "IDN", "name": "Indonesia", "baseline": 45, "lat": -0.8, "lng": 113.9},
    "VN": {"iso3": "VNM", "name": "Vietnam", "baseline": 38, "lat": 14.1, "lng": 108.3},
    "KR": {"iso3": "KOR", "name": "South Korea", "baseline": 28, "lat": 35.9, "lng": 127.8},
    "TW": {"iso3": "TWN", "name": "Taiwan", "baseline": 48, "lat": 23.7, "lng": 120.9},
}


class CountryRiskService:
    """Computes and maintains country risk scores."""

    # Weights for composite score
    W_CYBER = 0.35
    W_NEWS = 0.25
    W_BASELINE = 0.40

    UPDATE_INTERVAL = 30  # seconds

    def __init__(self) -> None:
        self._scores: Dict[str, CountryRisk] = {}
        self._attack_counts: Dict[str, int] = {}   # iso2 -> count in last 24h
        self._news_sentiments: Dict[str, float] = {}  # iso2 -> avg sentiment
        self._lock = asyncio.Lock()
        self._update_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._init_scores()

    def _init_scores(self) -> None:
        for iso2, info in _BASELINE.items():
            baseline = info["baseline"]
            self._scores[iso2] = CountryRisk(
                iso2=iso2,
                iso3=info["iso3"],
                name=info["name"],
                risk_score=baseline,
                cyber_score=0.0,
                news_score=50.0,
                stability_baseline=baseline,
                attack_count_24h=0,
                lat=info["lat"],
                lng=info["lng"],
            )

    async def start(self) -> None:
        self._update_task = asyncio.create_task(self._background_update())
        logger.info("CountryRiskService started for %d countries", len(_BASELINE))

    async def stop(self) -> None:
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_all_scores(self) -> List[CountryRisk]:
        async with self._lock:
            return sorted(
                self._scores.values(), key=lambda x: x.risk_score, reverse=True
            )

    async def get_country_score(self, iso2: str) -> Optional[CountryRisk]:
        async with self._lock:
            return self._scores.get(iso2.upper())

    async def record_attack(self, dest_country: str) -> None:
        """Record a cyber attack targeting a country (updates cyber score)."""
        iso2 = self._country_to_iso2(dest_country)
        if not iso2:
            return
        async with self._lock:
            self._attack_counts[iso2] = self._attack_counts.get(iso2, 0) + 1

    async def update_news_sentiment(
        self, country_name: str, sentiment: float
    ) -> None:
        """Feed news sentiment for a country (sentiment -1 to +1)."""
        iso2 = self._country_to_iso2(country_name)
        if not iso2:
            return
        async with self._lock:
            # Exponential moving average
            prev = self._news_sentiments.get(iso2, 0.0)
            self._news_sentiments[iso2] = prev * 0.9 + sentiment * 0.1

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    async def _background_update(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.UPDATE_INTERVAL)
                await self._recompute_scores()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Country risk update error: %s", exc)

    async def _recompute_scores(self) -> None:
        now = time.time()
        max_attacks = max(self._attack_counts.values(), default=1)

        async with self._lock:
            for iso2, score in self._scores.items():
                # Cyber score: normalize attack count to 0–100
                attacks = self._attack_counts.get(iso2, 0)
                cyber = min(100.0, (attacks / max(max_attacks, 1)) * 100)

                # News score: -1 (very negative) → 100, +1 (positive) → 0
                sentiment = self._news_sentiments.get(iso2, 0.0)
                news = (1 - sentiment) * 50  # convert -1..+1 to 0..100

                # Composite
                composite = (
                    self.W_CYBER * cyber
                    + self.W_NEWS * news
                    + self.W_BASELINE * score.stability_baseline
                )

                score.cyber_score = round(cyber, 1)
                score.news_score = round(news, 1)
                score.risk_score = round(min(100.0, composite), 1)
                score.attack_count_24h = attacks
                score.last_updated = now

        # Slowly decay attack counts
        async with self._lock:
            for iso2 in list(self._attack_counts.keys()):
                self._attack_counts[iso2] = max(0, self._attack_counts[iso2] - 1)

        # Persist snapshots to PostgreSQL (fire-and-forget, every ~5 min)
        if not hasattr(self, "_last_persist") or time.time() - self._last_persist > 300:
            self._last_persist = time.time()
            asyncio.create_task(self._persist_snapshots(list(self._scores.values())))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    _NAME_TO_ISO2: Dict[str, str] = {
        info["name"].lower(): iso2
        for iso2, info in _BASELINE.items()
    }
    # Add common variants
    _EXTRA_NAMES: Dict[str, str] = {
        "united states": "US", "usa": "US", "america": "US",
        "united kingdom": "GB", "uk": "GB", "britain": "GB",
        "russia": "RU", "china": "CN", "taiwan": "TW",
        "iran": "IR", "north korea": "KP", "south korea": "KR",
        "germany": "DE", "france": "FR", "israel": "IL",
        "ukraine": "UA", "brazil": "BR", "india": "IN",
        "australia": "AU", "canada": "CA", "japan": "JP",
    }

    def _country_to_iso2(self, name: str) -> Optional[str]:
        key = name.lower().strip()
        return (
            self._EXTRA_NAMES.get(key)
            or self._NAME_TO_ISO2.get(key)
            or (name.upper() if len(name) == 2 and name.upper() in _BASELINE else None)
        )

    @staticmethod
    async def _persist_snapshots(scores: "List[CountryRisk]") -> None:
        """Persist current risk scores as snapshots (for trend analysis)."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.intelligence import CountryRiskSnapshot
            async with AsyncSessionLocal() as session:
                for s in scores:
                    session.add(CountryRiskSnapshot(
                        iso2=s.iso2,
                        risk_score=s.risk_score,
                        cyber_score=s.cyber_score,
                        news_score=s.news_score,
                        attack_count_24h=s.attack_count_24h,
                    ))
                await session.commit()
        except Exception as exc:
            logger.debug("Country risk persistence error: %s", exc)


# Module-level singleton
country_risk_service = CountryRiskService()
