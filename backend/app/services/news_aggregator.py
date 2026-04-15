"""News aggregation service that fetches RSS feeds from major global sources.

Supports 40+ feeds across categories: world, tech, finance, security, geopolitics.
Results are cached in Redis (when available) with a configurable TTL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed registry – 40+ sources across categories
# ---------------------------------------------------------------------------

RSS_FEEDS: Dict[str, List[Dict[str, str]]] = {
    "world": [
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "region": "global"},
        {"name": "Reuters World", "url": "https://feeds.reuters.com/reuters/worldNews", "region": "global"},
        {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "region": "global"},
        {"name": "AP News", "url": "https://feeds.apnews.com/apnews/world", "region": "global"},
        {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss", "region": "global"},
        {"name": "DW World", "url": "https://rss.dw.com/rdf/rss-en-all", "region": "europe"},
        {"name": "France24", "url": "https://www.france24.com/en/rss", "region": "europe"},
        {"name": "NHK World", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "region": "asia"},
    ],
    "technology": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "region": "global"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss", "region": "global"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "region": "global"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "region": "global"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "region": "global"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/topnews.rss", "region": "global"},
        {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "region": "global"},
        {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "region": "global"},
    ],
    "finance": [
        {"name": "Financial Times", "url": "https://www.ft.com/rss/home/uk", "region": "global"},
        {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "region": "global"},
        {"name": "CNBC Finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "region": "global"},
        {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "region": "global"},
        {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "region": "global"},
        {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/realtimeheadlines/", "region": "global"},
        {"name": "Forbes Finance", "url": "https://www.forbes.com/investing/feed2/", "region": "global"},
        {"name": "Seeking Alpha", "url": "https://seekingalpha.com/feed.xml", "region": "global"},
    ],
    "security": [
        {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "region": "global"},
        {"name": "Schneier on Security", "url": "https://www.schneier.com/feed/atom", "region": "global"},
        {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "region": "global"},
        {"name": "Dark Reading", "url": "https://www.darkreading.com/rss.xml", "region": "global"},
        {"name": "SecurityWeek", "url": "https://www.securityweek.com/feed", "region": "global"},
        {"name": "Threatpost", "url": "https://threatpost.com/feed/", "region": "global"},
        {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "region": "global"},
        {"name": "CISA Alerts", "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml", "region": "us"},
    ],
    "geopolitics": [
        {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml", "region": "global"},
        {"name": "Foreign Policy", "url": "https://foreignpolicy.com/feed/", "region": "global"},
        {"name": "The Economist", "url": "https://www.economist.com/international/rss.xml", "region": "global"},
        {"name": "War on the Rocks", "url": "https://warontherocks.com/feed/", "region": "global"},
        {"name": "Defense One", "url": "https://www.defenseone.com/rss/all/", "region": "global"},
        {"name": "RAND Blog", "url": "https://www.rand.org/blog/articles.xml", "region": "global"},
        {"name": "Bellingcat", "url": "https://www.bellingcat.com/feed/", "region": "global"},
        {"name": "Crisis Group", "url": "https://www.crisisgroup.org/rss.xml", "region": "global"},
    ],
    "energy": [
        {"name": "Oil Price", "url": "https://oilprice.com/rss/main", "region": "global"},
        {"name": "Energy Monitor", "url": "https://www.energymonitor.ai/feed", "region": "global"},
        {"name": "Rigzone", "url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx", "region": "global"},
        {"name": "Reuters Energy", "url": "https://feeds.reuters.com/reuters/environment", "region": "global"},
    ],
    "health": [
        {"name": "WHO News", "url": "https://www.who.int/rss-feeds/news-english.xml", "region": "global"},
        {"name": "CDC Newsroom", "url": "https://tools.cdc.gov/api/v2/resources/media/403372.rss", "region": "us"},
        {"name": "STAT News", "url": "https://www.statnews.com/feed/", "region": "global"},
    ],
}

# Flat list of all feeds for easy iteration
ALL_FEEDS: List[Dict[str, str]] = [
    {**feed, "category": cat}
    for cat, feeds in RSS_FEEDS.items()
    for feed in feeds
]


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: str
    region: str
    published_at: float  # Unix timestamp
    tags: List[str] = field(default_factory=list)
    country_codes: List[str] = field(default_factory=list)
    sentiment_score: float = 0.0  # -1 (negative) to +1 (positive)
    relevance_score: float = 1.0


class NewsAggregator:
    """Aggregates news from RSS feeds with Redis caching and simple sentiment scoring."""

    # Negative-sentiment keywords for quick scoring
    _NEGATIVE_KEYWORDS = {
        "attack", "war", "conflict", "crisis", "killed", "dead", "disaster",
        "explosion", "missile", "bomb", "sanction", "threat", "hack", "breach",
        "collapse", "crash", "fail", "protest", "coup", "arrest", "fire",
        "flood", "earthquake", "hurricane", "pandemic", "outbreak",
    }
    _POSITIVE_KEYWORDS = {
        "peace", "agreement", "deal", "growth", "recovery", "breakthrough",
        "alliance", "cooperation", "record", "success", "advance", "invest",
    }

    CACHE_TTL = 300  # 5 minutes

    def __init__(self) -> None:
        self._cache: Dict[str, tuple[float, List[NewsItem]]] = {}
        self._all_items: List[NewsItem] = []
        self._redis: Optional[object] = None
        self._lock = asyncio.Lock()
        self._fetch_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def set_redis(self, redis_client: Optional[object]) -> None:
        self._redis = redis_client

    async def start(self) -> None:
        self._fetch_task = asyncio.create_task(self._background_fetch())
        logger.info("NewsAggregator started – fetching from %d feeds", len(ALL_FEEDS))

    async def stop(self) -> None:
        if self._fetch_task:
            self._fetch_task.cancel()
            try:
                await self._fetch_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_news(
        self,
        category: Optional[str] = None,
        limit: int = 30,
        region: Optional[str] = None,
    ) -> List[NewsItem]:
        """Return cached news items, optionally filtered."""
        async with self._lock:
            items = list(self._all_items)

        if category:
            items = [i for i in items if i.category == category]
        if region and region != "global":
            items = [i for i in items if i.region in (region, "global")]

        return sorted(items, key=lambda x: x.published_at, reverse=True)[:limit]

    async def get_categories(self) -> List[str]:
        return list(RSS_FEEDS.keys())

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    async def _background_fetch(self) -> None:
        while True:
            try:
                await self._fetch_all_feeds()
            except Exception as exc:
                logger.warning("News fetch cycle error: %s", exc)
            await asyncio.sleep(self.CACHE_TTL)

    async def _fetch_all_feeds(self) -> None:
        """Fetch all configured RSS feeds concurrently."""
        timeout = httpx.Timeout(10.0, connect=5.0)
        headers = {"User-Agent": "GlobalIntelDashboard/2.0 (news aggregator)"}

        items: List[NewsItem] = []

        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as client:
            tasks = [self._fetch_feed(client, feed) for feed in ALL_FEEDS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                items.extend(result)

        # Deduplicate by URL hash
        seen: set[str] = set()
        deduped: List[NewsItem] = []
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                deduped.append(item)

        # Sort by recency
        deduped.sort(key=lambda x: x.published_at, reverse=True)

        async with self._lock:
            self._all_items = deduped[:500]  # keep most recent 500

        logger.info("News aggregator: %d items refreshed", len(deduped))

        # Cache in Redis if available
        if self._redis:
            try:
                payload = json.dumps(
                    [self._item_to_dict(i) for i in deduped[:200]]
                )
                await self._redis.setex("intelligence:news", self.CACHE_TTL, payload)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("Redis news cache write failed: %s", exc)

        # Persist new items to PostgreSQL (fire-and-forget)
        asyncio.create_task(self._persist_news(deduped[:200]))

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed: Dict[str, str]
    ) -> List[NewsItem]:
        """Fetch and parse a single RSS feed."""
        try:
            resp = await client.get(feed["url"])
            resp.raise_for_status()
            return self._parse_rss(resp.text, feed)
        except Exception as exc:
            logger.debug("Feed fetch failed %s: %s", feed["name"], exc)
            return []

    def _parse_rss(
        self, xml_text: str, feed: Dict[str, str]
    ) -> List[NewsItem]:
        """Parse RSS/Atom XML into NewsItem objects (no external lib required)."""
        import xml.etree.ElementTree as ET

        items: List[NewsItem] = []
        try:
            # Handle XML namespaces loosely by stripping them for tag matching
            xml_text = xml_text.strip()
            # Remove default namespace declarations to simplify parsing
            import re
            xml_clean = re.sub(r' xmlns[^"]*"[^"]*"', "", xml_text)
            root = ET.fromstring(xml_clean)
        except ET.ParseError:
            return items

        # Support both RSS <item> and Atom <entry>
        ns_map = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/elements/1.1/",
        }
        entries = (
            root.findall(".//item")
            or root.findall(".//entry")
            or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        )

        for entry in entries[:20]:  # max 20 per feed
            title = self._text(entry, ["title"])
            link = (
                self._text(entry, ["link"])
                or self._attr(entry, "link", "href")
                or ""
            )
            summary = (
                self._text(entry, ["description", "summary", "content"])
                or ""
            )[:400]
            pub_date = self._text(entry, ["pubDate", "published", "updated", "dc:date"]) or ""

            if not title or not link:
                continue

            item_id = hashlib.md5(link.encode()).hexdigest()
            published_at = self._parse_date(pub_date)
            sentiment = self._score_sentiment(title + " " + summary)

            items.append(
                NewsItem(
                    id=item_id,
                    title=title.strip(),
                    summary=summary.strip(),
                    url=link,
                    source=feed["name"],
                    category=feed["category"],
                    region=feed.get("region", "global"),
                    published_at=published_at,
                    sentiment_score=sentiment,
                )
            )

        return items

    # ------------------------------------------------------------------
    # XML helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _text(element: object, tags: List[str]) -> str:
        import xml.etree.ElementTree as ET
        el = element  # type: ignore[assignment]
        for tag in tags:
            child = el.find(tag)  # type: ignore[union-attr]
            if child is not None and child.text:
                return child.text
        return ""

    @staticmethod
    def _attr(element: object, tag: str, attr: str) -> str:
        import xml.etree.ElementTree as ET
        el = element  # type: ignore[assignment]
        child = el.find(tag)  # type: ignore[union-attr]
        if child is not None:
            return child.get(attr, "")
        return ""

    @staticmethod
    def _parse_date(date_str: str) -> float:
        """Parse various date formats to Unix timestamp."""
        if not date_str:
            return time.time()
        from email.utils import parsedate_to_datetime
        from datetime import timezone
        try:
            return parsedate_to_datetime(date_str).timestamp()
        except Exception:
            pass
        import re
        # ISO 8601 – e.g. 2024-01-15T12:00:00Z
        match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", date_str)
        if match:
            from datetime import datetime
            try:
                return datetime.fromisoformat(match.group(1)).replace(
                    tzinfo=timezone.utc
                ).timestamp()
            except Exception:
                pass
        return time.time()

    def _score_sentiment(self, text: str) -> float:
        """Quick keyword-based sentiment score between -1.0 and +1.0."""
        words = set(text.lower().split())
        neg = len(words & self._NEGATIVE_KEYWORDS)
        pos = len(words & self._POSITIVE_KEYWORDS)
        total = neg + pos
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 2)

    @staticmethod
    def _item_to_dict(item: NewsItem) -> dict:  # type: ignore[type-arg]
        return {
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
            "source": item.source,
            "category": item.category,
            "region": item.region,
            "published_at": item.published_at,
            "sentiment_score": item.sentiment_score,
            "tags": item.tags,
            "country_codes": item.country_codes,
        }

    @staticmethod
    async def _persist_news(items: List[NewsItem]) -> None:
        """Upsert news items into PostgreSQL (fire-and-forget)."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.intelligence import NewsItemDB
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            async with AsyncSessionLocal() as session:
                for item in items:
                    stmt = pg_insert(NewsItemDB).values(
                        id=item.id,
                        title=item.title[:1000],
                        summary=(item.summary or "")[:2000],
                        url=item.url[:2000],
                        source=item.source,
                        category=item.category,
                        region=item.region,
                        published_at=item.published_at,
                        sentiment_score=item.sentiment_score,
                    ).on_conflict_do_nothing(index_elements=["id"])
                    await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.debug("News persistence error: %s", exc)


# Module-level singleton
news_aggregator = NewsAggregator()
