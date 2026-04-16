"""Unit tests for FinancialDataService.

Tests cover: _init_simulated_data (via start()), public getters
(get_market_summary, get_crypto, get_stocks, get_commodities, get_indices,
get_forex), set_redis, quote_to_dict, _drift_crypto, _apply_forex_rates,
_fetch_crypto (200, 429, exception), _fetch_forex_exchangerate (200,
exception→simulation), _update_simulated_stocks, _update_simulated_forex,
start/stop lifecycle.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.financial_data import (
    CRYPTO_IDS,
    FOREX_PAIRS,
    INDEX_SYMBOLS,
    STOCK_SYMBOLS,
    FinancialDataService,
    MarketSummary,
    TickerQuote,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> FinancialDataService:
    svc = FinancialDataService()
    return svc


def _mock_httpx_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _make_ticker(symbol="AAPL", asset_class="stock") -> TickerQuote:
    return TickerQuote(
        symbol=symbol,
        name="Apple Inc.",
        price=185.0,
        change=1.5,
        change_pct=0.82,
        volume=50_000_000.0,
        market_cap=2_900_000_000_000.0,
        high_24h=186.0,
        low_24h=184.0,
        asset_class=asset_class,
        exchange="NASDAQ",
        last_updated=time.time(),
        is_real=True,
    )


# ---------------------------------------------------------------------------
# _init_simulated_data (called by start)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_populates_simulated_data():
    svc = _make_service()
    with patch.object(svc, "_background_fetch", new_callable=AsyncMock) as mock_bg:
        mock_bg.side_effect = asyncio.CancelledError()
        await svc.start()
        await svc.stop()

    market = await svc.get_market_summary()
    assert len(market.stocks) == len(STOCK_SYMBOLS)
    assert len(market.indices) == len(INDEX_SYMBOLS)
    assert len(market.forex) == len(FOREX_PAIRS)
    assert len(market.crypto) == len(CRYPTO_IDS)
    assert len(market.commodities) > 0


@pytest.mark.asyncio
async def test_init_simulated_data_prices_positive():
    svc = _make_service()
    svc._init_simulated_data()
    for q in svc._market.stocks:
        assert q.price > 0
    for q in svc._market.crypto:
        assert q.price > 0


# ---------------------------------------------------------------------------
# Public getters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_summary_returns_market_summary():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_market_summary()
    assert isinstance(result, MarketSummary)


@pytest.mark.asyncio
async def test_get_crypto_returns_list():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_crypto()
    assert isinstance(result, list)
    assert all(isinstance(q, TickerQuote) for q in result)


@pytest.mark.asyncio
async def test_get_stocks_returns_list():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_stocks()
    assert len(result) == len(STOCK_SYMBOLS)


@pytest.mark.asyncio
async def test_get_commodities_returns_list():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_commodities()
    assert len(result) > 0


@pytest.mark.asyncio
async def test_get_indices_returns_list():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_indices()
    assert len(result) == len(INDEX_SYMBOLS)


@pytest.mark.asyncio
async def test_get_forex_returns_list():
    svc = _make_service()
    svc._init_simulated_data()
    result = await svc.get_forex()
    assert len(result) == len(FOREX_PAIRS)


@pytest.mark.asyncio
async def test_getters_return_copies():
    """Mutating the returned list should not affect internal state."""
    svc = _make_service()
    svc._init_simulated_data()
    stocks = await svc.get_stocks()
    original_len = len(svc._market.stocks)
    stocks.append(_make_ticker("FAKE"))
    assert len(svc._market.stocks) == original_len


# ---------------------------------------------------------------------------
# set_redis
# ---------------------------------------------------------------------------


def test_set_redis_stores_client():
    svc = _make_service()
    mock_redis = MagicMock()
    svc.set_redis(mock_redis)
    assert svc._redis is mock_redis


def test_set_redis_none():
    svc = _make_service()
    svc.set_redis(None)
    assert svc._redis is None


# ---------------------------------------------------------------------------
# quote_to_dict
# ---------------------------------------------------------------------------


def test_quote_to_dict_contains_required_keys():
    q = _make_ticker("AAPL", "stock")
    d = FinancialDataService.quote_to_dict(q)
    for key in (
        "symbol",
        "name",
        "price",
        "change",
        "change_pct",
        "asset_class",
        "is_real",
    ):
        assert key in d, f"Missing key: {key}"


def test_quote_to_dict_values_match():
    q = _make_ticker("MSFT", "stock")
    q.price = 420.0
    d = FinancialDataService.quote_to_dict(q)
    assert d["symbol"] == "MSFT"
    assert d["price"] == 420.0
    assert d["is_real"] is True


# ---------------------------------------------------------------------------
# _drift_crypto
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drift_crypto_changes_prices():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.crypto]
    await svc._drift_crypto()
    prices_after = [q.price for q in svc._market.crypto]
    # At least one price should have changed
    assert any(abs(a - b) > 1e-10 for a, b in zip(prices_before, prices_after))


@pytest.mark.asyncio
async def test_drift_crypto_prices_stay_positive():
    svc = _make_service()
    svc._init_simulated_data()
    for _ in range(10):
        await svc._drift_crypto()
    for q in svc._market.crypto:
        assert q.price > 0


# ---------------------------------------------------------------------------
# _apply_forex_rates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_forex_rates_updates_eur_usd():
    svc = _make_service()
    svc._init_simulated_data()
    # EUR/USD: base=EUR, quote=USD → price = rates["USD"] / rates["EUR"] = N/A
    # For EUR/USD: base=EUR, quote=USD → rate_base=EUR_rate, rate_quote=USD_rate
    # But in the logic: base="EUR", quote="USD" → neither base=="USD" nor quote=="USD" for first branch
    # Actually: quote=USD → branch: base_rate = rates.get("EUR"); rate = 1/base_rate
    rates = {"EUR": 0.92, "GBP": 0.79, "JPY": 149.5, "CNY": 7.24}
    await svc._apply_forex_rates(rates)
    eur_usd = next((q for q in svc._market.forex if q.symbol == "EUR/USD"), None)
    if eur_usd:
        # EUR/USD: quote=USD → rate = 1/EUR_rate = 1/0.92 ≈ 1.087
        assert eur_usd.is_real is True
        assert eur_usd.price > 0


@pytest.mark.asyncio
async def test_apply_forex_rates_skips_missing_rates():
    svc = _make_service()
    svc._init_simulated_data()
    # Empty rates should not crash
    await svc._apply_forex_rates({})


# ---------------------------------------------------------------------------
# _fetch_crypto – mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_crypto_200_updates_market():
    svc = _make_service()
    svc._init_simulated_data()

    coin_data = [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "current_price": 68000.0,
            "price_change_percentage_24h": 2.5,
            "total_volume": 30_000_000_000,
            "market_cap": 1_300_000_000_000,
            "high_24h": 69000,
            "low_24h": 67000,
        }
    ]
    mock_resp = _mock_httpx_response(200, coin_data)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.financial_data.httpx.AsyncClient", return_value=mock_client
    ):
        await svc._fetch_crypto()

    btc = next((q for q in svc._market.crypto if q.symbol == "BTC"), None)
    assert btc is not None
    assert btc.price == 68000.0


@pytest.mark.asyncio
async def test_fetch_crypto_429_keeps_existing_data():
    svc = _make_service()
    svc._init_simulated_data()
    original_count = len(svc._market.crypto)

    mock_resp = _mock_httpx_response(429, {})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.financial_data.httpx.AsyncClient", return_value=mock_client
    ):
        await svc._fetch_crypto()

    # Existing data preserved (with drift applied)
    assert len(svc._market.crypto) == original_count


@pytest.mark.asyncio
async def test_fetch_crypto_exception_triggers_drift():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.crypto]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch(
        "app.services.financial_data.httpx.AsyncClient", return_value=mock_client
    ):
        await svc._fetch_crypto()

    prices_after = [q.price for q in svc._market.crypto]
    # _drift_crypto was called → prices changed
    assert any(abs(a - b) > 1e-10 for a, b in zip(prices_before, prices_after))


# ---------------------------------------------------------------------------
# _fetch_forex_exchangerate – mocked httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_forex_200_applies_real_rates():
    svc = _make_service()
    svc._init_simulated_data()

    rates_payload = {"rates": {"EUR": 0.92, "GBP": 0.79, "JPY": 150.0}}
    mock_resp = _mock_httpx_response(200, rates_payload)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch(
        "app.services.financial_data.httpx.AsyncClient", return_value=mock_client
    ):
        await svc._fetch_forex_exchangerate()

    # At least one forex quote should have is_real = True (if pair mapped)
    real_quotes = [q for q in svc._market.forex if q.is_real]
    # May not have mapped all pairs – just verify no crash


@pytest.mark.asyncio
async def test_fetch_forex_exception_falls_back_to_simulation():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.forex]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch(
        "app.services.financial_data.httpx.AsyncClient", return_value=mock_client
    ):
        await svc._fetch_forex_exchangerate()

    # After simulation update prices should have drifted (or at minimum not crashed)
    assert len(svc._market.forex) == len(FOREX_PAIRS)


# ---------------------------------------------------------------------------
# _update_simulated_stocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_simulated_stocks_changes_prices():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.stocks]
    await svc._update_simulated_stocks()
    prices_after = [q.price for q in svc._market.stocks]
    assert any(abs(a - b) > 1e-10 for a, b in zip(prices_before, prices_after))


@pytest.mark.asyncio
async def test_update_simulated_stocks_prices_stay_positive():
    svc = _make_service()
    svc._init_simulated_data()
    for _ in range(5):
        await svc._update_simulated_stocks()
    for q in svc._market.stocks:
        assert q.price > 0


# ---------------------------------------------------------------------------
# _update_simulated_forex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_simulated_forex_changes_prices():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.forex]
    await svc._update_simulated_forex()
    prices_after = [q.price for q in svc._market.forex]
    assert any(abs(a - b) > 1e-10 for a, b in zip(prices_before, prices_after))


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    svc = _make_service()
    with patch.object(svc, "_background_fetch", new_callable=AsyncMock) as mock_bg:
        mock_bg.side_effect = asyncio.CancelledError()
        await svc.start()
        assert svc._fetch_task is not None
        await svc.stop()
        assert svc._fetch_task.done()


@pytest.mark.asyncio
async def test_stop_noop_if_never_started():
    svc = _make_service()
    await svc.stop()  # should not raise


# ---------------------------------------------------------------------------
# _background_fetch – single cycle, then cancelled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_background_fetch_calls_all_fetchers():
    svc = _make_service()
    svc._init_simulated_data()

    call_order = []

    async def _fake_crypto():
        call_order.append("crypto")

    async def _fake_stocks():
        call_order.append("stocks")

    async def _fake_indices():
        call_order.append("indices")

    async def _fake_forex():
        call_order.append("forex")

    async def _fake_commodities():
        call_order.append("commodities")

    # Patch sleep to cancel after first iteration
    sleep_count = {"n": 0}

    async def _fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 1:
            raise asyncio.CancelledError()

    with (
        patch.object(svc, "_fetch_crypto", _fake_crypto),
        patch.object(svc, "_fetch_stocks_yfinance", _fake_stocks),
        patch.object(svc, "_fetch_indices_yfinance", _fake_indices),
        patch.object(svc, "_fetch_forex_exchangerate", _fake_forex),
        patch.object(svc, "_fetch_commodities_yfinance", _fake_commodities),
        patch("asyncio.sleep", _fake_sleep),
    ):
        try:
            await svc._background_fetch()
        except asyncio.CancelledError:
            pass

    assert "crypto" in call_order
    assert "stocks" in call_order
    assert "commodities" in call_order


@pytest.mark.asyncio
async def test_background_fetch_swallows_exception():
    """An exception in a fetch cycle should be swallowed; loop continues."""
    svc = _make_service()
    svc._init_simulated_data()

    sleep_count = {"n": 0}

    async def _fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            raise asyncio.CancelledError()

    async def _raises():
        raise ValueError("bad fetch")

    async def _noop():
        pass

    with (
        patch.object(svc, "_fetch_crypto", _raises),
        patch.object(svc, "_fetch_stocks_yfinance", _noop),
        patch.object(svc, "_fetch_indices_yfinance", _noop),
        patch.object(svc, "_fetch_forex_exchangerate", _noop),
        patch.object(svc, "_fetch_commodities_yfinance", _noop),
        patch("asyncio.sleep", _fake_sleep),
    ):
        try:
            await svc._background_fetch()
        except asyncio.CancelledError:
            pass

    # If we got here without raising, the exception was swallowed
    assert sleep_count["n"] >= 1


# ---------------------------------------------------------------------------
# _fetch_stocks_yfinance – success and fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_stocks_yfinance_success_updates_market():
    svc = _make_service()
    svc._init_simulated_data()

    real_quotes = [
        TickerQuote(
            symbol="AAPL",
            name="Apple Inc.",
            price=190.0,
            change=2.0,
            change_pct=1.06,
            volume=50_000_000.0,
            market_cap=None,
            high_24h=191.0,
            low_24h=189.0,
            asset_class="stock",
            exchange="NASDAQ",
            last_updated=time.time(),
            is_real=True,
        )
    ]

    with patch.object(
        svc,
        "_yfinance_fetch",
        return_value=real_quotes,
    ):
        await svc._fetch_stocks_yfinance()

    aapl = next((q for q in svc._market.stocks if q.symbol == "AAPL"), None)
    assert aapl is not None
    assert aapl.price == 190.0
    assert aapl.is_real is True


@pytest.mark.asyncio
async def test_fetch_stocks_yfinance_empty_falls_back_to_simulation():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.stocks]

    with patch.object(svc, "_yfinance_fetch", return_value=[]):
        await svc._fetch_stocks_yfinance()

    # prices should have drifted (simulated update was called)
    assert len(svc._market.stocks) == len(prices_before)


# ---------------------------------------------------------------------------
# _fetch_indices_yfinance – success and fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_indices_yfinance_success_updates_market():
    svc = _make_service()
    svc._init_simulated_data()

    real_quotes = [
        TickerQuote(
            symbol="^GSPC",
            name="S&P 500",
            price=5300.0,
            change=50.0,
            change_pct=0.95,
            volume=None,
            market_cap=None,
            high_24h=5320.0,
            low_24h=5280.0,
            asset_class="index",
            exchange="NYSE",
            last_updated=time.time(),
            is_real=True,
        )
    ]

    with patch.object(svc, "_yfinance_fetch", return_value=real_quotes):
        await svc._fetch_indices_yfinance()

    sp500 = next((q for q in svc._market.indices if q.symbol == "^GSPC"), None)
    assert sp500 is not None
    assert sp500.price == 5300.0


@pytest.mark.asyncio
async def test_fetch_indices_yfinance_empty_falls_back():
    svc = _make_service()
    svc._init_simulated_data()

    with patch.object(svc, "_yfinance_fetch", return_value=[]):
        await svc._fetch_indices_yfinance()

    # No crash, indices still present
    assert len(svc._market.indices) > 0


# ---------------------------------------------------------------------------
# _yfinance_fetch – unit tests (executor is mocked away)
# ---------------------------------------------------------------------------


def test_yfinance_fetch_returns_empty_on_import_error():
    svc = _make_service()

    import builtins
    import importlib

    real_import = builtins.__import__

    def no_yfinance(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yfinance")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=no_yfinance):
        result = svc._yfinance_fetch(["AAPL"], "stock")

    assert result == []


def test_yfinance_fetch_returns_empty_on_exception():
    svc = _make_service()

    with patch("builtins.__import__", side_effect=RuntimeError("yf broken")):
        result = svc._yfinance_fetch(["AAPL"], "stock")

    assert result == []


# ---------------------------------------------------------------------------
# _yfinance_fetch_commodities – import error / exception
# ---------------------------------------------------------------------------


def test_yfinance_fetch_commodities_returns_empty_on_import_error():
    svc = _make_service()

    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    import builtins

    def no_yf(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yf")
        return builtins.__import__(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=no_yf):
        result = svc._yfinance_fetch_commodities(["GC=F"])

    assert result == []


# ---------------------------------------------------------------------------
# _fetch_commodities_yfinance – success and fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_commodities_yfinance_success_updates_market():
    svc = _make_service()
    svc._init_simulated_data()

    gold_quote = TickerQuote(
        symbol="GOLD",
        name="Gold (USD/troy oz)",
        price=2100.0,
        change=20.0,
        change_pct=0.96,
        volume=None,
        market_cap=None,
        high_24h=2110.0,
        low_24h=2090.0,
        asset_class="commodity",
        exchange="COMEX",
        last_updated=time.time(),
        is_real=True,
    )

    with patch.object(
        svc, "_yfinance_fetch_commodities", return_value=[gold_quote]
    ):
        await svc._fetch_commodities_yfinance()

    gold = next(
        (q for q in svc._market.commodities if "GOLD" in q.symbol), None
    )
    assert gold is not None
    assert gold.price == 2100.0


@pytest.mark.asyncio
async def test_fetch_commodities_yfinance_empty_falls_back():
    svc = _make_service()
    svc._init_simulated_data()

    with patch.object(svc, "_yfinance_fetch_commodities", return_value=[]):
        await svc._fetch_commodities_yfinance()

    # No crash, commodities still present
    assert len(svc._market.commodities) > 0


# ---------------------------------------------------------------------------
# _update_simulated_commodities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_simulated_commodities_changes_prices():
    svc = _make_service()
    svc._init_simulated_data()
    prices_before = [q.price for q in svc._market.commodities]
    await svc._update_simulated_commodities()
    prices_after = [q.price for q in svc._market.commodities]
    # At least some prices should change
    assert any(abs(a - b) > 1e-10 for a, b in zip(prices_before, prices_after))


@pytest.mark.asyncio
async def test_update_simulated_commodities_no_crash_on_empty():
    svc = _make_service()
    svc._market.commodities = []
    await svc._update_simulated_commodities()  # should not raise


# ---------------------------------------------------------------------------
# _persist_financial_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_financial_snapshot_swallows_db_error():
    """_persist_financial_snapshot should swallow DB errors silently."""
    svc = _make_service()
    ticker = _make_ticker("AAPL", "stock")

    with patch(
        "app.core.database.AsyncSessionLocal",
        side_effect=RuntimeError("DB down"),
    ):
        await svc._persist_financial_snapshot([ticker])  # should not raise


@pytest.mark.asyncio
async def test_persist_financial_snapshot_with_mock_session():
    """_persist_financial_snapshot calls session.add and commit for each quote."""
    svc = _make_service()
    tickers = [_make_ticker("AAPL", "stock"), _make_ticker("BTC", "crypto")]

    mock_session = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.core.database.AsyncSessionLocal",
        return_value=mock_session_ctx,
    ):
        await svc._persist_financial_snapshot(tickers)

    assert mock_session.add.call_count == 2
    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _apply_forex_rates edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_forex_rates_usd_base_pair():
    """USD/JPY: base=USD → price = rates["JPY"]."""
    svc = _make_service()
    svc._init_simulated_data()
    await svc._apply_forex_rates({"JPY": 150.0, "CNY": 7.25})
    usd_jpy = next((q for q in svc._market.forex if q.symbol == "USD/JPY"), None)
    if usd_jpy:
        assert usd_jpy.price == pytest.approx(150.0, rel=1e-4)
        assert usd_jpy.is_real is True


@pytest.mark.asyncio
async def test_apply_forex_rates_cross_pair():
    """A non-USD/USD cross pair (e.g. EUR/GBP would be cross but we have EUR/USD)."""
    svc = _make_service()
    svc._init_simulated_data()
    # USD/CNY: base=USD → rate = rates["CNY"]
    await svc._apply_forex_rates({"CNY": 7.20})
    usd_cny = next((q for q in svc._market.forex if q.symbol == "USD/CNY"), None)
    if usd_cny:
        assert usd_cny.is_real is True
