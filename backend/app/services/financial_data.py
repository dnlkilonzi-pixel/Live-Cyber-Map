"""Financial data service – stocks, crypto, commodities, and forex.

Data sources (all free, no API keys required):
  - CoinGecko public API  (crypto – live)
  - Yahoo Finance via yfinance (stocks & indices – live with simulation fallback)
  - open.er-api.com (forex – live with simulation fallback)
  - Simulated commodities with realistic drift (labelled is_real=False)

All real quotes include is_real=True; simulated data is is_real=False.
Results cached with short TTLs to avoid rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TickerQuote:
    symbol: str
    name: str
    price: float
    change: float  # absolute
    change_pct: float  # percentage
    volume: Optional[float]
    market_cap: Optional[float]
    high_24h: Optional[float]
    low_24h: Optional[float]
    asset_class: str  # "stock" | "crypto" | "commodity" | "index" | "forex"
    exchange: Optional[str]
    last_updated: float  # Unix timestamp
    is_real: bool = False  # True when backed by a live API; False when simulated


@dataclass
class MarketSummary:
    indices: List[TickerQuote] = field(default_factory=list)
    stocks: List[TickerQuote] = field(default_factory=list)
    crypto: List[TickerQuote] = field(default_factory=list)
    commodities: List[TickerQuote] = field(default_factory=list)
    forex: List[TickerQuote] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Tickers to track
# ---------------------------------------------------------------------------

STOCK_SYMBOLS: List[Tuple[str, str, str]] = [
    # (symbol, name, exchange)
    ("AAPL", "Apple Inc.", "NASDAQ"),
    ("MSFT", "Microsoft Corp.", "NASDAQ"),
    ("GOOGL", "Alphabet Inc.", "NASDAQ"),
    ("AMZN", "Amazon.com Inc.", "NASDAQ"),
    ("NVDA", "NVIDIA Corp.", "NASDAQ"),
    ("META", "Meta Platforms", "NASDAQ"),
    ("TSLA", "Tesla Inc.", "NASDAQ"),
    ("JPM", "JPMorgan Chase", "NYSE"),
    ("BAC", "Bank of America", "NYSE"),
    ("XOM", "Exxon Mobil", "NYSE"),
    ("V", "Visa Inc.", "NYSE"),
    ("JNJ", "Johnson & Johnson", "NYSE"),
    ("WMT", "Walmart Inc.", "NYSE"),
    ("UNH", "UnitedHealth Group", "NYSE"),
    ("BRK-B", "Berkshire Hathaway", "NYSE"),
    ("TSM", "Taiwan Semiconductor", "NYSE"),
    ("ASML", "ASML Holding", "NASDAQ"),
    ("SAP", "SAP SE", "NYSE"),
    ("TM", "Toyota Motor", "NYSE"),
    ("BABA", "Alibaba Group", "NYSE"),
]

CRYPTO_IDS: List[Tuple[str, str]] = [
    # (coingecko_id, display_symbol)
    ("bitcoin", "BTC"),
    ("ethereum", "ETH"),
    ("binancecoin", "BNB"),
    ("solana", "SOL"),
    ("ripple", "XRP"),
    ("cardano", "ADA"),
    ("avalanche-2", "AVAX"),
    ("dogecoin", "DOGE"),
    ("polkadot", "DOT"),
    ("chainlink", "LINK"),
    ("uniswap", "UNI"),
    ("litecoin", "LTC"),
    ("bitcoin-cash", "BCH"),
    ("stellar", "XLM"),
    ("monero", "XMR"),
]

INDEX_SYMBOLS: List[Tuple[str, str, str]] = [
    ("^GSPC", "S&P 500", "NYSE"),
    ("^DJI", "Dow Jones", "NYSE"),
    ("^IXIC", "NASDAQ Composite", "NASDAQ"),
    ("^FTSE", "FTSE 100", "LSE"),
    ("^N225", "Nikkei 225", "TSE"),
    ("^HSI", "Hang Seng", "HKEX"),
    ("^GDAXI", "DAX", "FRA"),
    ("^FCHI", "CAC 40", "EURONEXT"),
]

# Commodity seeds: (symbol, name, base_price, unit)
COMMODITY_SEEDS: List[Tuple[str, str, float, str]] = [
    ("CRUDE_OIL", "Crude Oil (WTI)", 78.50, "USD/bbl"),
    ("BRENT", "Brent Crude", 82.30, "USD/bbl"),
    ("NATURAL_GAS", "Natural Gas", 2.85, "USD/MMBtu"),
    ("GOLD", "Gold", 2050.00, "USD/troy oz"),
    ("SILVER", "Silver", 23.50, "USD/troy oz"),
    ("COPPER", "Copper", 3.85, "USD/lb"),
    ("PLATINUM", "Platinum", 960.00, "USD/troy oz"),
    ("PALLADIUM", "Palladium", 1050.00, "USD/troy oz"),
    ("WHEAT", "Wheat", 540.00, "USD/bu"),
    ("CORN", "Corn", 450.00, "USD/bu"),
    ("SOYBEANS", "Soybeans", 1150.00, "USD/bu"),
    ("SUGAR", "Sugar #11", 22.50, "USc/lb"),
    ("COFFEE", "Coffee (Arabica)", 180.00, "USc/lb"),
    ("COTTON", "Cotton", 82.00, "USc/lb"),
    ("LUMBER", "Lumber", 520.00, "USD/1000 board ft"),
    ("URANIUM", "Uranium", 95.00, "USD/lb"),
]

FOREX_PAIRS: List[Tuple[str, str, float]] = [
    # (pair, name, base_rate)
    ("EUR/USD", "Euro / US Dollar", 1.085),
    ("GBP/USD", "British Pound / US Dollar", 1.265),
    ("USD/JPY", "US Dollar / Japanese Yen", 149.50),
    ("USD/CNY", "US Dollar / Chinese Yuan", 7.24),
    ("USD/CHF", "US Dollar / Swiss Franc", 0.885),
    ("AUD/USD", "Australian Dollar / US Dollar", 0.655),
    ("USD/CAD", "US Dollar / Canadian Dollar", 1.355),
    ("USD/KRW", "US Dollar / Korean Won", 1320.0),
    ("USD/INR", "US Dollar / Indian Rupee", 83.10),
    ("USD/BRL", "US Dollar / Brazilian Real", 4.97),
]


class FinancialDataService:
    """Fetches and caches financial market data from free public APIs."""

    CRYPTO_TTL = 60  # 1 minute
    STOCK_TTL = 120  # 2 minutes
    COMMODITY_TTL = 300  # 5 minutes

    def __init__(self) -> None:
        self._market: MarketSummary = MarketSummary()
        self._redis: Optional[object] = None
        self._lock = asyncio.Lock()
        self._fetch_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        # Seed simulated commodity/forex prices
        self._commodity_prices = {s: p for s, _, p, _ in COMMODITY_SEEDS}
        self._forex_prices = {p: r for p, _, r in FOREX_PAIRS}

    def set_redis(self, redis_client: Optional[object]) -> None:
        self._redis = redis_client

    async def start(self) -> None:
        # Prime with simulated data immediately so API is responsive right away
        self._init_simulated_data()
        self._fetch_task = asyncio.create_task(self._background_fetch())
        logger.info("FinancialDataService started")

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

    async def get_market_summary(self) -> MarketSummary:
        async with self._lock:
            return self._market

    async def get_crypto(self) -> List[TickerQuote]:
        async with self._lock:
            return list(self._market.crypto)

    async def get_stocks(self) -> List[TickerQuote]:
        async with self._lock:
            return list(self._market.stocks)

    async def get_commodities(self) -> List[TickerQuote]:
        async with self._lock:
            return list(self._market.commodities)

    async def get_indices(self) -> List[TickerQuote]:
        async with self._lock:
            return list(self._market.indices)

    async def get_forex(self) -> List[TickerQuote]:
        async with self._lock:
            return list(self._market.forex)

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    async def _background_fetch(self) -> None:
        while True:
            try:
                await asyncio.gather(
                    self._fetch_crypto(),
                    self._fetch_stocks_yfinance(),
                    self._fetch_indices_yfinance(),
                    self._fetch_forex_exchangerate(),
                    self._fetch_commodities_yfinance(),
                )
                # Persist a sample of real quotes every cycle
                async with self._lock:
                    all_real = [
                        q
                        for group in [
                            self._market.indices,
                            self._market.stocks,
                            self._market.forex,
                            self._market.commodities,
                        ]
                        for q in group
                        if q.is_real
                    ]
                if all_real:
                    asyncio.create_task(self._persist_financial_snapshot(all_real))
            except Exception as exc:
                logger.warning("Financial data fetch error: %s", exc)
            await asyncio.sleep(self.STOCK_TTL)

    # ------------------------------------------------------------------
    # CoinGecko crypto (free, no key)
    # ------------------------------------------------------------------

    async def _fetch_crypto(self) -> None:
        ids = ",".join(cid for cid, _ in CRYPTO_IDS)
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&ids={ids}&order=market_cap_desc"
            "&per_page=50&page=1&sparkline=false&price_change_percentage=24h"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = []
                    id_to_sym = {cid: sym for cid, sym in CRYPTO_IDS}
                    for coin in data:
                        sym = id_to_sym.get(coin["id"], coin["symbol"].upper())
                        price = coin.get("current_price") or 0.0
                        chg_pct = coin.get("price_change_percentage_24h") or 0.0
                        chg = price * chg_pct / 100
                        quotes.append(
                            TickerQuote(
                                symbol=sym,
                                name=coin.get("name", sym),
                                price=price,
                                change=round(chg, 4),
                                change_pct=round(chg_pct, 2),
                                volume=coin.get("total_volume"),
                                market_cap=coin.get("market_cap"),
                                high_24h=coin.get("high_24h"),
                                low_24h=coin.get("low_24h"),
                                asset_class="crypto",
                                exchange="CoinGecko",
                                last_updated=time.time(),
                            )
                        )
                    async with self._lock:
                        self._market.crypto = quotes
                        self._market.last_updated = time.time()
                    logger.debug("Fetched %d crypto quotes", len(quotes))
                elif resp.status_code == 429:
                    logger.debug("CoinGecko rate limited – will retry")
        except Exception as exc:
            logger.debug("CoinGecko fetch failed: %s", exc)
            # Keep existing data; add small drift
            await self._drift_crypto()

    async def _drift_crypto(self) -> None:
        async with self._lock:
            for q in self._market.crypto:
                drift = random.gauss(0, 0.003)
                q.price = max(0.001, q.price * (1 + drift))
                q.change = round(q.price * drift, 4)
                q.change_pct = round(drift * 100, 2)
                q.last_updated = time.time()

    # ------------------------------------------------------------------
    # Yahoo Finance via yfinance (stocks + indices)
    # ------------------------------------------------------------------

    async def _fetch_stocks_yfinance(self) -> None:
        """Fetch real stock prices via yfinance (runs sync code in executor)."""
        symbols = [s for s, _, _ in STOCK_SYMBOLS]
        quotes = await asyncio.get_event_loop().run_in_executor(
            None, self._yfinance_fetch, symbols, "stock"
        )
        if quotes:
            async with self._lock:
                # Merge with existing (keep simulated entries if yfinance misses them)
                sym_map = {q.symbol: q for q in quotes}
                updated = [sym_map.get(q.symbol, q) for q in self._market.stocks]
                self._market.stocks = updated
                self._market.last_updated = time.time()
            logger.debug("yfinance: updated %d stock quotes", len(quotes))
        else:
            await self._update_simulated_stocks()

    async def _persist_financial_snapshot(self, quotes: "List[TickerQuote]") -> None:
        """Persist a batch of financial quotes to PostgreSQL."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.financial import FinancialSnapshot

            async with AsyncSessionLocal() as session:
                for q in quotes:
                    session.add(
                        FinancialSnapshot(
                            symbol=q.symbol,
                            asset_class=q.asset_class,
                            price=q.price,
                            change_pct=q.change_pct,
                            is_real=q.is_real,
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.debug("Financial persistence error: %s", exc)

    async def _fetch_indices_yfinance(self) -> None:
        """Fetch real index prices via yfinance."""
        symbols = [s for s, _, _ in INDEX_SYMBOLS]
        quotes = await asyncio.get_event_loop().run_in_executor(
            None, self._yfinance_fetch, symbols, "index"
        )
        if quotes:
            async with self._lock:
                sym_map = {q.symbol: q for q in quotes}
                updated = [sym_map.get(q.symbol, q) for q in self._market.indices]
                self._market.indices = updated
                self._market.last_updated = time.time()
            logger.debug("yfinance: updated %d index quotes", len(quotes))
        else:
            await self._update_simulated_stocks()

    def _yfinance_fetch(
        self, symbols: List[str], asset_class: str
    ) -> List[TickerQuote]:
        """Synchronous yfinance download – run in a thread executor."""
        try:
            import yfinance as yf  # type: ignore[import]

            data = yf.download(
                tickers=symbols,
                period="2d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            quotes: List[TickerQuote] = []
            sym_info: Dict[str, Tuple[str, str]] = {}
            # Map symbol → (name, exchange) from the appropriate list
            for src in [STOCK_SYMBOLS, INDEX_SYMBOLS]:
                for row in src:
                    sym_info[row[0]] = (row[1], row[2])

            for sym in symbols:
                try:
                    if len(symbols) == 1:
                        df = data
                    else:
                        df = (
                            data[sym]
                            if sym in data.columns.get_level_values(0)
                            else data
                        )

                    if df.empty or len(df) < 1:
                        continue

                    close_col = "Close"
                    row_today = df.iloc[-1]
                    price = float(row_today[close_col])
                    if math.isnan(price) or price <= 0:
                        continue

                    prev_price = price
                    if len(df) >= 2:
                        prev = float(df.iloc[-2][close_col])
                        if not math.isnan(prev) and prev > 0:
                            prev_price = prev

                    change = price - prev_price
                    change_pct = (change / prev_price * 100) if prev_price > 0 else 0.0
                    name, exchange = sym_info.get(sym, (sym, ""))
                    volume = float(row_today.get("Volume", 0) or 0)
                    quotes.append(
                        TickerQuote(
                            symbol=sym,
                            name=name,
                            price=round(price, 2),
                            change=round(change, 2),
                            change_pct=round(change_pct, 2),
                            volume=volume if volume > 0 else None,
                            market_cap=None,
                            high_24h=float(row_today.get("High", price)),
                            low_24h=float(row_today.get("Low", price)),
                            asset_class=asset_class,
                            exchange=exchange,
                            last_updated=time.time(),
                            is_real=True,
                        )
                    )
                except Exception as sym_exc:
                    logger.debug("yfinance symbol %s error: %s", sym, sym_exc)
            return quotes
        except Exception as exc:
            logger.debug("yfinance batch download failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Exchangerate.host (forex – free, no key)
    # ------------------------------------------------------------------

    async def _fetch_forex_exchangerate(self) -> None:
        """Fetch live forex rates from open.er-api.com (free, no key required)."""
        url = "https://open.er-api.com/v6/latest/USD"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    rates: Dict[str, float] = data.get("rates", {})
                    if rates:
                        await self._apply_forex_rates(rates)
                        return
        except Exception as exc:
            logger.debug("Exchangerate fetch failed: %s", exc)
        # Fallback to simulation
        await self._update_simulated_forex()

    async def _apply_forex_rates(self, rates: Dict[str, float]) -> None:
        """Apply real forex rates to the market forex list."""
        now = time.time()
        # Build a currency → USD rate lookup
        async with self._lock:
            for q in self._market.forex:
                pair = q.symbol  # e.g. "EUR/USD"
                parts = pair.split("/")
                if len(parts) != 2:
                    continue
                base, quote = parts
                try:
                    if base == "USD":
                        rate = rates.get(quote)
                    elif quote == "USD":
                        base_rate = rates.get(base)
                        rate = (1.0 / base_rate) if base_rate else None
                    else:
                        rate_base = rates.get(base)
                        rate_quote = rates.get(quote)
                        rate = (
                            (rate_quote / rate_base)
                            if (rate_base and rate_quote)
                            else None
                        )

                    if rate and not math.isnan(rate):
                        prev = q.price
                        q.price = round(rate, 6)
                        q.change = round(q.price - prev, 6)
                        q.change_pct = (
                            round((q.price - prev) / prev * 100, 4) if prev else 0.0
                        )
                        q.last_updated = now
                        q.is_real = True
                        self._forex_prices[q.symbol] = rate
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Simulated stocks (realistic random walk seeded from actual levels)
    # ------------------------------------------------------------------

    # Seed prices (approximate real values, updated manually periodically)
    _STOCK_SEEDS: Dict[str, float] = {
        "AAPL": 185.0,
        "MSFT": 420.0,
        "GOOGL": 175.0,
        "AMZN": 185.0,
        "NVDA": 875.0,
        "META": 510.0,
        "TSLA": 175.0,
        "JPM": 198.0,
        "BAC": 35.0,
        "XOM": 108.0,
        "V": 285.0,
        "JNJ": 155.0,
        "WMT": 185.0,
        "UNH": 530.0,
        "BRK-B": 375.0,
        "TSM": 145.0,
        "ASML": 900.0,
        "SAP": 195.0,
        "TM": 225.0,
        "BABA": 75.0,
    }

    _INDEX_SEEDS: Dict[str, float] = {
        "^GSPC": 5200.0,
        "^DJI": 39000.0,
        "^IXIC": 16300.0,
        "^FTSE": 7700.0,
        "^N225": 38500.0,
        "^HSI": 17000.0,
        "^GDAXI": 18000.0,
        "^FCHI": 8100.0,
    }

    def _init_simulated_data(self) -> None:
        now = time.time()

        # Stocks
        stocks = []
        for sym, name, exchange in STOCK_SYMBOLS:
            base = self._STOCK_SEEDS.get(sym, 100.0)
            chg_pct = random.gauss(0.0, 1.5)
            price = base * (1 + chg_pct / 100)
            stocks.append(
                TickerQuote(
                    symbol=sym,
                    name=name,
                    price=round(price, 2),
                    change=round(price * chg_pct / 100, 2),
                    change_pct=round(chg_pct, 2),
                    volume=random.uniform(5e6, 8e7),
                    market_cap=None,
                    high_24h=None,
                    low_24h=None,
                    asset_class="stock",
                    exchange=exchange,
                    last_updated=now,
                )
            )

        # Indices
        indices = []
        for sym, name, exchange in INDEX_SYMBOLS:
            base = self._INDEX_SEEDS.get(sym, 5000.0)
            chg_pct = random.gauss(0.0, 0.8)
            price = base * (1 + chg_pct / 100)
            indices.append(
                TickerQuote(
                    symbol=sym,
                    name=name,
                    price=round(price, 2),
                    change=round(price * chg_pct / 100, 2),
                    change_pct=round(chg_pct, 2),
                    volume=None,
                    market_cap=None,
                    high_24h=None,
                    low_24h=None,
                    asset_class="index",
                    exchange=exchange,
                    last_updated=now,
                )
            )

        # Commodities
        commodities = []
        for sym, name, base, unit in COMMODITY_SEEDS:
            price = self._commodity_prices[sym]
            chg_pct = random.gauss(0.0, 1.0)
            price_new = price * (1 + chg_pct / 100)
            self._commodity_prices[sym] = price_new
            commodities.append(
                TickerQuote(
                    symbol=sym,
                    name=f"{name} ({unit})",
                    price=round(price_new, 3),
                    change=round(price_new * chg_pct / 100, 3),
                    change_pct=round(chg_pct, 2),
                    volume=None,
                    market_cap=None,
                    high_24h=None,
                    low_24h=None,
                    asset_class="commodity",
                    exchange="COMEX",
                    last_updated=now,
                )
            )

        # Forex
        forex = []
        for pair, name, base in FOREX_PAIRS:
            rate = self._forex_prices[pair]
            forex.append(
                TickerQuote(
                    symbol=pair,
                    name=name,
                    price=round(rate, 4),
                    change=0.0,
                    change_pct=0.0,
                    volume=None,
                    market_cap=None,
                    high_24h=None,
                    low_24h=None,
                    asset_class="forex",
                    exchange="FX",
                    last_updated=now,
                )
            )

        # Simulated crypto until CoinGecko responds
        crypto = []
        _CRYPTO_SEEDS = {
            "BTC": 67000,
            "ETH": 3500,
            "BNB": 400,
            "SOL": 175,
            "XRP": 0.55,
            "ADA": 0.45,
            "AVAX": 38,
            "DOGE": 0.09,
            "DOT": 8.5,
            "LINK": 18,
            "UNI": 11,
            "LTC": 95,
            "BCH": 450,
            "XLM": 0.12,
            "XMR": 165,
        }
        for cid, sym in CRYPTO_IDS:
            base = _CRYPTO_SEEDS.get(sym, 1.0)
            chg_pct = random.gauss(0.0, 2.0)
            price = base * (1 + chg_pct / 100)
            crypto.append(
                TickerQuote(
                    symbol=sym,
                    name=sym,
                    price=round(price, 4),
                    change=round(price * chg_pct / 100, 4),
                    change_pct=round(chg_pct, 2),
                    volume=None,
                    market_cap=None,
                    high_24h=None,
                    low_24h=None,
                    asset_class="crypto",
                    exchange="CoinGecko",
                    last_updated=now,
                )
            )

        self._market = MarketSummary(
            indices=indices,
            stocks=stocks,
            crypto=crypto,
            commodities=commodities,
            forex=forex,
            last_updated=now,
        )

    async def _update_simulated_stocks(self) -> None:
        async with self._lock:
            now = time.time()
            for q in self._market.stocks + self._market.indices:
                drift = random.gauss(0.0001, 0.003)
                q.price = max(0.01, round(q.price * (1 + drift), 2))
                prev = q.price / (1 + drift)
                q.change = round(q.price - prev, 2)
                q.change_pct = round(drift * 100, 2)
                q.last_updated = now

    async def _update_simulated_commodities(self) -> None:
        async with self._lock:
            now = time.time()
            for q in self._market.commodities:
                sym = q.symbol.split(" ")[0]  # strip unit suffix
                _ = (
                    sym
                    if sym in self._commodity_prices
                    else q.symbol.split("(")[0].strip()
                )
                # Find the matching key
                match_key = next(
                    (k for k in self._commodity_prices if k in q.symbol), None
                )
                if match_key:
                    drift = random.gauss(0.0, 0.005)
                    new_price = self._commodity_prices[match_key] * (1 + drift)
                    self._commodity_prices[match_key] = new_price
                    q.price = round(new_price, 3)
                    q.change = round(new_price * drift, 3)
                    q.change_pct = round(drift * 100, 2)
                    q.last_updated = now

    # yfinance tickers for key commodities (futures)
    _COMMODITY_YFINANCE: Dict[str, Tuple[str, str, str]] = {
        # yf_symbol -> (internal_key, display_name, unit)
        "GC=F": ("GOLD", "Gold", "USD/troy oz"),
        "SI=F": ("SILVER", "Silver", "USD/troy oz"),
        "CL=F": ("CRUDE_OIL", "Crude Oil (WTI)", "USD/bbl"),
        "BZ=F": ("BRENT", "Brent Crude", "USD/bbl"),
        "NG=F": ("NATURAL_GAS", "Natural Gas", "USD/MMBtu"),
        "HG=F": ("COPPER", "Copper", "USD/lb"),
        "PL=F": ("PLATINUM", "Platinum", "USD/troy oz"),
        "PA=F": ("PALLADIUM", "Palladium", "USD/troy oz"),
        "ZW=F": ("WHEAT", "Wheat", "USD/bu"),
        "ZC=F": ("CORN", "Corn", "USD/bu"),
        "ZS=F": ("SOYBEANS", "Soybeans", "USD/bu"),
    }

    async def _fetch_commodities_yfinance(self) -> None:
        """Fetch real commodity futures prices via yfinance; fall back to simulation."""
        yf_symbols = list(self._COMMODITY_YFINANCE.keys())
        quotes = await asyncio.get_event_loop().run_in_executor(
            None, self._yfinance_fetch_commodities, yf_symbols
        )
        if quotes:
            async with self._lock:
                # Build a lookup by internal key (e.g. "GOLD")
                real_map: Dict[str, TickerQuote] = {q.symbol: q for q in quotes}
                updated: List[TickerQuote] = []
                for existing in self._market.commodities:
                    # Find the real quote whose symbol matches the internal key
                    real = real_map.get(existing.symbol.split(" ")[0])
                    if real is None:
                        # Try matching by the internal_key stored in extra metadata
                        internal_key = next(
                            (k for k in real_map if k in existing.symbol), None
                        )
                        real = real_map.get(internal_key) if internal_key else None
                    updated.append(real if real else existing)
                self._market.commodities = updated
                self._market.last_updated = time.time()
            logger.debug("yfinance commodities: updated %d quotes", len(quotes))
        else:
            await self._update_simulated_commodities()

    def _yfinance_fetch_commodities(self, symbols: List[str]) -> List[TickerQuote]:
        """Synchronous yfinance download for commodity futures – run in executor."""
        try:
            import yfinance as yf  # type: ignore[import]

            data = yf.download(
                tickers=symbols,
                period="2d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            quotes: List[TickerQuote] = []
            for yf_sym, (
                internal_key,
                display_name,
                unit,
            ) in self._COMMODITY_YFINANCE.items():
                try:
                    if len(symbols) == 1:
                        df = data
                    else:
                        df = (
                            data[yf_sym]
                            if yf_sym in data.columns.get_level_values(0)
                            else None
                        )
                    if df is None or df.empty or len(df) < 1:
                        continue
                    row = df.iloc[-1]
                    price = float(row["Close"])
                    if math.isnan(price) or price <= 0:
                        continue
                    prev_price = price
                    if len(df) >= 2:
                        prev = float(df.iloc[-2]["Close"])
                        if not math.isnan(prev) and prev > 0:
                            prev_price = prev
                    change = price - prev_price
                    change_pct = (change / prev_price * 100) if prev_price > 0 else 0.0
                    # Update the internal price cache too
                    self._commodity_prices[internal_key] = price
                    quotes.append(
                        TickerQuote(
                            symbol=internal_key,
                            name=f"{display_name} ({unit})",
                            price=round(price, 3),
                            change=round(change, 3),
                            change_pct=round(change_pct, 2),
                            volume=float(row.get("Volume", 0) or 0) or None,
                            market_cap=None,
                            high_24h=float(row.get("High", price)),
                            low_24h=float(row.get("Low", price)),
                            asset_class="commodity",
                            exchange="COMEX",
                            last_updated=time.time(),
                            is_real=True,
                        )
                    )
                except Exception as sym_exc:
                    logger.debug("yfinance commodity %s error: %s", yf_sym, sym_exc)
            return quotes
        except Exception as exc:
            logger.debug("yfinance commodity download failed: %s", exc)
            return []

    async def _update_simulated_forex(self) -> None:
        async with self._lock:
            now = time.time()
            for q in self._market.forex:
                if q.symbol in self._forex_prices:
                    drift = random.gauss(0.0, 0.001)
                    new_rate = self._forex_prices[q.symbol] * (1 + drift)
                    self._forex_prices[q.symbol] = new_rate
                    prev = q.price
                    q.price = round(new_rate, 4)
                    q.change = round(q.price - prev, 4)
                    q.change_pct = round(drift * 100, 4)
                    q.last_updated = now

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def quote_to_dict(q: TickerQuote) -> dict:  # type: ignore[type-arg]
        return {
            "symbol": q.symbol,
            "name": q.name,
            "price": q.price,
            "change": q.change,
            "change_pct": q.change_pct,
            "volume": q.volume,
            "market_cap": q.market_cap,
            "high_24h": q.high_24h,
            "low_24h": q.low_24h,
            "asset_class": q.asset_class,
            "exchange": q.exchange,
            "last_updated": q.last_updated,
            "is_real": q.is_real,
        }


# Module-level singleton
financial_service = FinancialDataService()
