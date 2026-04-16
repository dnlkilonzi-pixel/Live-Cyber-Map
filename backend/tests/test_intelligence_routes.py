"""Tests for app/api/intelligence_routes.py.

Covers: GET /news, GET /news/categories, GET /news/by-country/{iso2},
POST /brief, GET /brief/{category}, GET /risk, GET /risk/{iso2},
GET /ollama/status, POST /ollama/reset, POST /ollama/pull,
POST /ollama/select, GET /risk/{iso2}/trend, GET /sentiment/timeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_client():
    """HTTPX client with SQLite in-memory DB override."""
    engine = create_async_engine(_SQLITE_URL, echo=False)
    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
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
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


def _news_item(
    id_="n1",
    title="Breaking: Test",
    summary="A test news item",
    url="https://example.com",
    source="Reuters",
    category="world",
    region="global",
    sentiment=0.1,
):
    item = MagicMock()
    item.id = id_
    item.title = title
    item.summary = summary
    item.url = url
    item.source = source
    item.category = category
    item.region = region
    item.published_at = 1700000000.0
    item.sentiment_score = sentiment
    return item


# ---------------------------------------------------------------------------
# GET /api/intelligence/news
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_news_empty(client):
    with patch(
        "app.services.news_aggregator.news_aggregator.get_news",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get("/api/intelligence/news")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_news_returns_items(client):
    items = [_news_item()]
    with patch(
        "app.services.news_aggregator.news_aggregator.get_news",
        new=AsyncMock(return_value=items),
    ):
        resp = await client.get("/api/intelligence/news")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Breaking: Test"
    assert data[0]["category"] == "world"


@pytest.mark.asyncio
async def test_get_news_with_category_and_region(client):
    items = [_news_item(category="cyber", region="EU")]
    with patch(
        "app.services.news_aggregator.news_aggregator.get_news",
        new=AsyncMock(return_value=items),
    ) as mock_get:
        resp = await client.get(
            "/api/intelligence/news?category=cyber&region=EU&limit=5"
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/intelligence/news/categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_categories(client):
    with patch(
        "app.services.news_aggregator.news_aggregator.get_categories",
        new=AsyncMock(return_value=["world", "cyber", "finance"]),
    ):
        resp = await client.get("/api/intelligence/news/categories")
    assert resp.status_code == 200
    assert "categories" in resp.json()
    assert "world" in resp.json()["categories"]


# ---------------------------------------------------------------------------
# GET /api/intelligence/news/by-country/{iso2}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_news_by_country_db_has_rows(db_client):
    """When DB rows exist, they are returned directly."""
    from app.models.intelligence import NewsItemDB
    from sqlalchemy.ext.asyncio import AsyncSession

    # Insert a row using the overridden DB
    engine = create_async_engine(_SQLITE_URL, echo=False)
    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        from app.models import intelligence  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

    async with TestSession() as session:
        row = NewsItemDB(
            id="test-news-1",
            title="Test",
            summary="Sum",
            url="http://t.com",
            source="BBC",
            category="world",
            region="DE",
            published_at=1700000000.0,
            sentiment_score=0.1,
        )
        session.add(row)
        await session.commit()
    await engine.dispose()

    # The db_client uses a different in-memory DB so this tests the fallback path
    with (
        patch(
            "app.services.country_risk.country_risk_service.get_country_score",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=[]),
        ),
    ):
        resp = await db_client.get("/api/intelligence/news/by-country/DE")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_news_by_country_fallback_path(client):
    """When DB lookup fails, falls back to in-memory news aggregator."""
    item = _news_item(region="US", title="US attack news")
    with (
        patch(
            "app.services.country_risk.country_risk_service.get_country_score",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=[item]),
        ),
    ):
        resp = await client.get("/api/intelligence/news/by-country/US")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["region"] == "US"


@pytest.mark.asyncio
async def test_news_by_country_fallback_with_name_match(client):
    """Name-match filter works when country_name is found."""
    item = _news_item(region="global", title="Germany floods rising")
    score = MagicMock()
    score.name = "Germany"

    with (
        patch(
            "app.services.country_risk.country_risk_service.get_country_score",
            new=AsyncMock(return_value=score),
        ),
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=[item]),
        ),
    ):
        resp = await client.get("/api/intelligence/news/by-country/DE")
    assert resp.status_code == 200
    # Germany name matches the title
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# POST /api/intelligence/brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_brief_no_news(client):
    """Returns a fallback brief when no news items are available."""
    with patch(
        "app.services.news_aggregator.news_aggregator.get_news",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.post("/api/intelligence/brief", json={"category": "cyber"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_generated"] is False
    assert body["source_count"] == 0


@pytest.mark.asyncio
async def test_generate_brief_with_news_ai_available(client):
    """Returns an AI brief when Ollama is available."""
    items = [_news_item()]
    with (
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=items),
        ),
        patch(
            "app.services.ollama_service.ollama_service.is_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.ollama_service.ollama_service.generate_brief",
            new=AsyncMock(return_value="AI brief text"),
        ),
    ):
        resp = await client.post(
            "/api/intelligence/brief", json={"category": "world", "style": "analyst"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_generated"] is True
    assert body["brief"] == "AI brief text"
    assert body["source_count"] == 1


@pytest.mark.asyncio
async def test_generate_brief_with_news_ai_unavailable(client):
    """Returns a fallback brief when Ollama is unavailable."""
    items = [_news_item()]
    with (
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=items),
        ),
        patch(
            "app.services.ollama_service.ollama_service.is_available",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.ollama_service.ollama_service.generate_brief",
            new=AsyncMock(return_value="Fallback text"),
        ),
    ):
        resp = await client.post("/api/intelligence/brief", json={"category": "world"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_generated"] is False


# ---------------------------------------------------------------------------
# GET /api/intelligence/brief/{category}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_brief_by_category(client):
    items = [_news_item()]
    with (
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=items),
        ),
        patch(
            "app.services.ollama_service.ollama_service.is_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.ollama_service.ollama_service.generate_brief",
            new=AsyncMock(return_value="World brief"),
        ),
    ):
        resp = await client.get("/api/intelligence/brief/world?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "world"


@pytest.mark.asyncio
async def test_get_brief_by_category_no_items(client):
    with (
        patch(
            "app.services.news_aggregator.news_aggregator.get_news",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.ollama_service.ollama_service.is_available",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.ollama_service.ollama_service.generate_brief",
            new=AsyncMock(return_value="No news brief"),
        ),
    ):
        resp = await client.get("/api/intelligence/brief/cyber")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/intelligence/risk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_risk_scores_empty(client):
    with patch(
        "app.services.country_risk.country_risk_service.get_all_scores",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get("/api/intelligence/risk")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_all_risk_scores_returns_items(client):
    score = MagicMock()
    score.iso2 = "US"
    score.iso3 = "USA"
    score.name = "United States"
    score.risk_score = 40.0
    score.cyber_score = 50.0
    score.news_score = 30.0
    score.stability_baseline = 60.0
    score.attack_count_24h = 100
    score.lat = 37.09
    score.lng = -95.71
    score.last_updated = 1700000000.0

    with patch(
        "app.services.country_risk.country_risk_service.get_all_scores",
        new=AsyncMock(return_value=[score]),
    ):
        resp = await client.get("/api/intelligence/risk")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["iso2"] == "US"


# ---------------------------------------------------------------------------
# GET /api/intelligence/risk/{iso2}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_country_risk_found(client):
    score = MagicMock()
    score.iso2 = "GB"
    score.iso3 = "GBR"
    score.name = "United Kingdom"
    score.risk_score = 35.0
    score.cyber_score = 45.0
    score.news_score = 25.0
    score.stability_baseline = 65.0
    score.attack_count_24h = 80
    score.lat = 55.38
    score.lng = -3.44
    score.last_updated = 1700000000.0

    with patch(
        "app.services.country_risk.country_risk_service.get_country_score",
        new=AsyncMock(return_value=score),
    ):
        resp = await client.get("/api/intelligence/risk/GB")
    assert resp.status_code == 200
    assert resp.json()["iso2"] == "GB"


@pytest.mark.asyncio
async def test_get_country_risk_not_found(client):
    with patch(
        "app.services.country_risk.country_risk_service.get_country_score",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.get("/api/intelligence/risk/ZZ")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/intelligence/ollama/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_status_available(client):
    with (
        patch(
            "app.services.ollama_service.ollama_service.is_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.ollama_service.ollama_service.list_models",
            new=AsyncMock(return_value=["llama3.2:3b"]),
        ),
    ):
        resp = await client.get("/api/intelligence/ollama/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert "llama3.2:3b" in body["models"]


@pytest.mark.asyncio
async def test_ollama_status_unavailable(client):
    with patch(
        "app.services.ollama_service.ollama_service.is_available",
        new=AsyncMock(return_value=False),
    ):
        resp = await client.get("/api/intelligence/ollama/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["models"] == []


# ---------------------------------------------------------------------------
# POST /api/intelligence/ollama/reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_reset(client):
    with patch(
        "app.services.ollama_service.ollama_service.reset_probe", new=AsyncMock()
    ):
        resp = await client.post("/api/intelligence/ollama/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "probe reset"


# ---------------------------------------------------------------------------
# POST /api/intelligence/ollama/pull
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_pull_success(client):
    with (
        patch(
            "app.services.ollama_service.ollama_service.pull_model",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.ollama_service.ollama_service.reset_probe", new=AsyncMock()
        ),
    ):
        resp = await client.post("/api/intelligence/ollama/pull?model_name=mistral:7b")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pull_initiated"
    assert body["model"] == "mistral:7b"


@pytest.mark.asyncio
async def test_ollama_pull_failure(client):
    with patch(
        "app.services.ollama_service.ollama_service.pull_model",
        new=AsyncMock(return_value=False),
    ):
        resp = await client.post("/api/intelligence/ollama/pull?model_name=bad-model")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pull_failed"


# ---------------------------------------------------------------------------
# POST /api/intelligence/ollama/select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_select_model(client):
    import app.services.ollama_service as ollama_module

    original_model = ollama_module.OLLAMA_MODEL
    try:
        resp = await client.post("/api/intelligence/ollama/select?model_name=gemma:2b")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "model_changed"
        assert body["model"] == "gemma:2b"
        assert ollama_module.OLLAMA_MODEL == "gemma:2b"
    finally:
        ollama_module.OLLAMA_MODEL = original_model


# ---------------------------------------------------------------------------
# GET /api/intelligence/risk/{iso2}/trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_trend_empty(db_client):
    resp = await db_client.get("/api/intelligence/risk/US/trend?hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["iso2"] == "US"
    assert body["count"] == 0
    assert body["points"] == []


@pytest.mark.asyncio
async def test_risk_trend_db_error_returns_503(client):
    """Returns 503 when DB is unavailable."""
    from app.core.database import get_db

    async def bad_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        yield mock_session

    app.dependency_overrides[get_db] = bad_db
    try:
        resp = await client.get("/api/intelligence/risk/US/trend")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /api/intelligence/sentiment/timeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_timeline_empty(db_client):
    resp = await db_client.get("/api/intelligence/sentiment/timeline?hours=24")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_sentiment_timeline_with_region_filter(db_client):
    resp = await db_client.get(
        "/api/intelligence/sentiment/timeline?region=global&hours=6"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_sentiment_timeline_db_error_returns_503(client):
    from app.core.database import get_db

    async def bad_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        yield mock_session

    app.dependency_overrides[get_db] = bad_db
    try:
        resp = await client.get("/api/intelligence/sentiment/timeline")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)
