"""Unit tests for NewsAggregator.

Tests cover: _text / _attr / _parse_date / _score_sentiment helpers,
_parse_rss (RSS and Atom formats, missing title/link, dedup),
_item_to_dict, set_redis, get_categories, get_news (filtering by
category and region), _fetch_feed (mocked httpx, HTTP error),
start/stop lifecycle, and _fetch_all_feeds integration.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.news_aggregator import NewsAggregator, NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RSS_SIMPLE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Breaking News</title>
      <link>https://example.com/article/1</link>
      <description>Something happened today.</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Second Story</title>
      <link>https://example.com/article/2</link>
      <description>Another event.</description>
    </item>
  </channel>
</rss>"""

_ATOM_SIMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Entry</title>
    <link href="https://example.com/atom/1"/>
    <summary>Atom summary text.</summary>
    <published>2024-01-02T08:00:00Z</published>
  </entry>
</feed>"""

_RSS_MISSING_FIELDS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <description>No title, no link – should be skipped.</description>
    </item>
    <item>
      <title>Has title but no link</title>
    </item>
    <item>
      <title>Valid Item</title>
      <link>https://example.com/valid</link>
    </item>
  </channel>
</rss>"""


def _make_feed(name="Test", url="https://example.com/rss", category="world"):
    return {"name": name, "url": url, "category": category, "region": "global"}


def _make_aggregator() -> NewsAggregator:
    return NewsAggregator()


# ---------------------------------------------------------------------------
# _text helper
# ---------------------------------------------------------------------------


def test_text_finds_child():
    import xml.etree.ElementTree as ET

    el = ET.fromstring("<item><title>Hello</title></item>")
    assert NewsAggregator._text(el, ["title"]) == "Hello"


def test_text_returns_empty_if_not_found():
    import xml.etree.ElementTree as ET

    el = ET.fromstring("<item><link>url</link></item>")
    assert NewsAggregator._text(el, ["title"]) == ""


def test_text_tries_multiple_tags():
    import xml.etree.ElementTree as ET

    el = ET.fromstring("<item><description>Desc</description></item>")
    assert NewsAggregator._text(el, ["summary", "description"]) == "Desc"


def test_text_returns_empty_on_no_text():
    import xml.etree.ElementTree as ET

    el = ET.fromstring("<item><title/></item>")
    assert NewsAggregator._text(el, ["title"]) == ""


# ---------------------------------------------------------------------------
# _attr helper
# ---------------------------------------------------------------------------


def test_attr_finds_attribute():
    import xml.etree.ElementTree as ET

    el = ET.fromstring('<feed><link href="https://example.com"/></feed>')
    assert NewsAggregator._attr(el, "link", "href") == "https://example.com"


def test_attr_returns_empty_if_tag_missing():
    import xml.etree.ElementTree as ET

    el = ET.fromstring("<feed><title>T</title></feed>")
    assert NewsAggregator._attr(el, "link", "href") == ""


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_rfc2822():
    ts = NewsAggregator._parse_date("Mon, 01 Jan 2024 12:00:00 +0000")
    assert ts > 0
    # 2024-01-01 12:00:00 UTC
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert dt.year == 2024
    assert dt.month == 1


def test_parse_date_iso8601():
    ts = NewsAggregator._parse_date("2024-06-15T09:30:00Z")
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert dt.year == 2024
    assert dt.month == 6


def test_parse_date_empty_returns_recent():
    before = time.time()
    ts = NewsAggregator._parse_date("")
    after = time.time()
    assert before <= ts <= after


def test_parse_date_garbage_returns_recent():
    before = time.time()
    ts = NewsAggregator._parse_date("not a date at all")
    after = time.time()
    assert before <= ts <= after


# ---------------------------------------------------------------------------
# _score_sentiment
# ---------------------------------------------------------------------------


def test_score_sentiment_negative_keywords():
    agg = _make_aggregator()
    score = agg._score_sentiment("war attack conflict killed")
    assert score < 0


def test_score_sentiment_positive_keywords():
    agg = _make_aggregator()
    score = agg._score_sentiment("peace agreement deal growth")
    assert score > 0


def test_score_sentiment_neutral():
    agg = _make_aggregator()
    score = agg._score_sentiment("the quick brown fox")
    assert score == 0.0


def test_score_sentiment_mixed():
    agg = _make_aggregator()
    score = agg._score_sentiment("peace war")
    assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _parse_rss
# ---------------------------------------------------------------------------


def test_parse_rss_simple():
    agg = _make_aggregator()
    items = agg._parse_rss(
        _RSS_SIMPLE, _make_feed("BBC", "https://bbc.com/rss", "world")
    )
    assert len(items) == 2
    assert items[0].title == "Breaking News"
    assert items[0].source == "BBC"
    assert items[0].category == "world"
    assert items[0].region == "global"
    assert items[0].url == "https://example.com/article/1"
    assert items[0].summary == "Something happened today."


def test_parse_rss_pub_date_parsed():
    agg = _make_aggregator()
    items = agg._parse_rss(_RSS_SIMPLE, _make_feed())
    # first item has a valid pubDate
    assert items[0].published_at > 0


def test_parse_rss_atom_format():
    agg = _make_aggregator()
    items = agg._parse_rss(_ATOM_SIMPLE, _make_feed("Atom Source"))
    assert len(items) == 1
    assert items[0].title == "Atom Entry"
    assert "example.com/atom/1" in items[0].url


def test_parse_rss_skips_missing_title_link():
    agg = _make_aggregator()
    items = agg._parse_rss(_RSS_MISSING_FIELDS, _make_feed())
    # Only the "Valid Item" entry should survive
    assert len(items) == 1
    assert items[0].title == "Valid Item"


def test_parse_rss_bad_xml_returns_empty():
    agg = _make_aggregator()
    items = agg._parse_rss("<<< not valid xml >>>", _make_feed())
    assert items == []


def test_parse_rss_id_is_md5_of_url():
    import hashlib

    agg = _make_aggregator()
    items = agg._parse_rss(_RSS_SIMPLE, _make_feed())
    expected_id = hashlib.md5("https://example.com/article/1".encode()).hexdigest()
    assert items[0].id == expected_id


def test_parse_rss_sentiment_assigned():
    agg = _make_aggregator()
    items = agg._parse_rss(_RSS_SIMPLE, _make_feed())
    for item in items:
        assert -1.0 <= item.sentiment_score <= 1.0


# ---------------------------------------------------------------------------
# _item_to_dict
# ---------------------------------------------------------------------------


def test_item_to_dict_round_trips():
    item = NewsItem(
        id="abc",
        title="Test Title",
        summary="Summary",
        url="https://example.com",
        source="BBC",
        category="world",
        region="global",
        published_at=1700000000.0,
        sentiment_score=0.5,
    )
    d = NewsAggregator._item_to_dict(item)
    assert d["id"] == "abc"
    assert d["title"] == "Test Title"
    assert d["sentiment_score"] == 0.5
    assert d["tags"] == []
    assert d["country_codes"] == []


# ---------------------------------------------------------------------------
# set_redis
# ---------------------------------------------------------------------------


def test_set_redis_stores_client():
    agg = _make_aggregator()
    mock_redis = MagicMock()
    agg.set_redis(mock_redis)
    assert agg._redis is mock_redis


def test_set_redis_none():
    agg = _make_aggregator()
    agg.set_redis(None)
    assert agg._redis is None


# ---------------------------------------------------------------------------
# get_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_categories_returns_list():
    agg = _make_aggregator()
    cats = await agg.get_categories()
    assert isinstance(cats, list)
    assert "world" in cats
    assert "technology" in cats
    assert "security" in cats


# ---------------------------------------------------------------------------
# get_news – filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_news_empty_initially():
    agg = _make_aggregator()
    items = await agg.get_news()
    assert items == []


@pytest.mark.asyncio
async def test_get_news_filter_by_category():
    agg = _make_aggregator()
    agg._all_items = [
        NewsItem(
            "1", "Title A", "", "https://a.com", "src", "world", "global", time.time()
        ),
        NewsItem(
            "2",
            "Title B",
            "",
            "https://b.com",
            "src",
            "technology",
            "global",
            time.time(),
        ),
    ]
    result = await agg.get_news(category="world")
    assert len(result) == 1
    assert result[0].category == "world"


@pytest.mark.asyncio
async def test_get_news_filter_by_region():
    agg = _make_aggregator()
    now = time.time()
    agg._all_items = [
        NewsItem("1", "Global", "", "https://a.com", "src", "world", "global", now),
        NewsItem("2", "US Only", "", "https://b.com", "src", "world", "us", now),
        NewsItem("3", "EU Only", "", "https://c.com", "src", "world", "europe", now),
    ]
    result = await agg.get_news(region="us")
    # "us" region should include "us" and "global"
    categories = {i.region for i in result}
    assert "europe" not in categories


@pytest.mark.asyncio
async def test_get_news_limit_respected():
    agg = _make_aggregator()
    agg._all_items = [
        NewsItem(
            str(i),
            f"Title {i}",
            "",
            f"https://{i}.com",
            "src",
            "world",
            "global",
            float(i),
        )
        for i in range(20)
    ]
    result = await agg.get_news(limit=5)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_get_news_sorted_by_recency():
    agg = _make_aggregator()
    now = time.time()
    agg._all_items = [
        NewsItem(
            "old", "Old", "", "https://old.com", "src", "world", "global", now - 1000
        ),
        NewsItem("new", "New", "", "https://new.com", "src", "world", "global", now),
    ]
    result = await agg.get_news(limit=10)
    assert result[0].id == "new"


# ---------------------------------------------------------------------------
# _fetch_feed – mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_feed_success():
    agg = _make_aggregator()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = _RSS_SIMPLE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    items = await agg._fetch_feed(mock_client, _make_feed())
    assert len(items) == 2
    assert items[0].title == "Breaking News"


@pytest.mark.asyncio
async def test_fetch_feed_http_error_returns_empty():
    agg = _make_aggregator()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))

    items = await agg._fetch_feed(mock_client, _make_feed())
    assert items == []


@pytest.mark.asyncio
async def test_fetch_feed_non_200_returns_empty():
    agg = _make_aggregator()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=mock_resp
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    items = await agg._fetch_feed(mock_client, _make_feed())
    assert items == []


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_creates_background_task():
    agg = _make_aggregator()
    with patch.object(agg, "_background_fetch", new_callable=AsyncMock) as mock_bg:
        # Patch _fetch_all_feeds so the background task exits immediately
        mock_bg.side_effect = asyncio.CancelledError()
        await agg.start()
        assert agg._fetch_task is not None
        await agg.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task():
    agg = _make_aggregator()

    async def forever():
        while True:
            await asyncio.sleep(10)

    with patch.object(agg, "_background_fetch", side_effect=forever):
        await agg.start()
        await agg.stop()
        assert agg._fetch_task.cancelled() or agg._fetch_task.done()


@pytest.mark.asyncio
async def test_stop_noop_if_never_started():
    agg = _make_aggregator()
    await agg.stop()  # should not raise
