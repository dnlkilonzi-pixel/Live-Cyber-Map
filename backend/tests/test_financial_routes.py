"""Tests for app/api/financial_routes.py – all 6 endpoints."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.financial_data import MarketSummary, TickerQuote


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_ticker(symbol: str, asset_class: str) -> TickerQuote:
    return TickerQuote(
        symbol=symbol,
        name=f"{symbol} Name",
        price=100.0,
        change=1.0,
        change_pct=1.0,
        volume=1_000_000.0,
        market_cap=None,
        high_24h=101.0,
        low_24h=99.0,
        asset_class=asset_class,
        exchange="TEST",
        last_updated=time.time(),
        is_real=True,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# GET /api/financial/crypto
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_crypto_returns_list(client):
    tickers = [_make_ticker("BTC", "crypto"), _make_ticker("ETH", "crypto")]
    with patch(
        "app.services.financial_data.financial_service.get_crypto",
        new_callable=AsyncMock,
        return_value=tickers,
    ):
        resp = await client.get("/api/financial/crypto")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["symbol"] == "BTC"
    assert body[0]["asset_class"] == "crypto"


@pytest.mark.asyncio
async def test_get_crypto_empty(client):
    with patch(
        "app.services.financial_data.financial_service.get_crypto",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/financial/crypto")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/financial/stocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stocks_returns_list(client):
    tickers = [_make_ticker("AAPL", "stock"), _make_ticker("MSFT", "stock")]
    with patch(
        "app.services.financial_data.financial_service.get_stocks",
        new_callable=AsyncMock,
        return_value=tickers,
    ):
        resp = await client.get("/api/financial/stocks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    symbols = [b["symbol"] for b in body]
    assert "AAPL" in symbols
    assert "MSFT" in symbols


# ---------------------------------------------------------------------------
# GET /api/financial/commodities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_commodities_returns_list(client):
    tickers = [_make_ticker("GOLD", "commodity")]
    with patch(
        "app.services.financial_data.financial_service.get_commodities",
        new_callable=AsyncMock,
        return_value=tickers,
    ):
        resp = await client.get("/api/financial/commodities")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["symbol"] == "GOLD"


# ---------------------------------------------------------------------------
# GET /api/financial/indices
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_indices_returns_list(client):
    tickers = [_make_ticker("^GSPC", "index"), _make_ticker("^DJI", "index")]
    with patch(
        "app.services.financial_data.financial_service.get_indices",
        new_callable=AsyncMock,
        return_value=tickers,
    ):
        resp = await client.get("/api/financial/indices")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2


# ---------------------------------------------------------------------------
# GET /api/financial/forex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_forex_returns_list(client):
    tickers = [_make_ticker("EUR/USD", "forex"), _make_ticker("USD/JPY", "forex")]
    with patch(
        "app.services.financial_data.financial_service.get_forex",
        new_callable=AsyncMock,
        return_value=tickers,
    ):
        resp = await client.get("/api/financial/forex")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    symbols = [b["symbol"] for b in body]
    assert "EUR/USD" in symbols


# ---------------------------------------------------------------------------
# GET /api/financial/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_summary_returns_all_categories(client):
    summary = MarketSummary(
        indices=[_make_ticker("^GSPC", "index")],
        stocks=[_make_ticker("AAPL", "stock")],
        crypto=[_make_ticker("BTC", "crypto")],
        commodities=[_make_ticker("GOLD", "commodity")],
        forex=[_make_ticker("EUR/USD", "forex")],
        last_updated=time.time(),
    )
    with patch(
        "app.services.financial_data.financial_service.get_market_summary",
        new_callable=AsyncMock,
        return_value=summary,
    ):
        resp = await client.get("/api/financial/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "indices" in body
    assert "stocks" in body
    assert "crypto" in body
    assert "commodities" in body
    assert "forex" in body
    assert "last_updated" in body
    assert len(body["indices"]) == 1
    assert body["indices"][0]["symbol"] == "^GSPC"


@pytest.mark.asyncio
async def test_get_market_summary_empty(client):
    summary = MarketSummary()
    with patch(
        "app.services.financial_data.financial_service.get_market_summary",
        new_callable=AsyncMock,
        return_value=summary,
    ):
        resp = await client.get("/api/financial/summary")
    assert resp.status_code == 200
    body = resp.json()
    for cat in ("indices", "stocks", "crypto", "commodities", "forex"):
        assert body[cat] == []


@pytest.mark.asyncio
async def test_ticker_response_fields_populated(client):
    """Verify all TickerResponse fields are present in the response."""
    ticker = _make_ticker("BTC", "crypto")
    with patch(
        "app.services.financial_data.financial_service.get_crypto",
        new_callable=AsyncMock,
        return_value=[ticker],
    ):
        resp = await client.get("/api/financial/crypto")
    assert resp.status_code == 200
    item = resp.json()[0]
    for field in (
        "symbol",
        "name",
        "price",
        "change",
        "change_pct",
        "volume",
        "market_cap",
        "high_24h",
        "low_24h",
        "asset_class",
        "exchange",
        "last_updated",
        "is_real",
    ):
        assert field in item, f"Missing field: {field}"
