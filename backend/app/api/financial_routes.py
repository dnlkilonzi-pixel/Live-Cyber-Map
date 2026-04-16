"""Financial data REST API routes – stocks, crypto, commodities, forex."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TickerResponse(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: float | None
    market_cap: float | None
    high_24h: float | None
    low_24h: float | None
    asset_class: str
    exchange: str | None
    last_updated: float
    is_real: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/crypto",
    response_model=List[TickerResponse],
    tags=["financial"],
    summary="Get cryptocurrency prices",
)
async def get_crypto():
    from app.services.financial_data import FinancialDataService, financial_service

    quotes = await financial_service.get_crypto()
    return [TickerResponse(**FinancialDataService.quote_to_dict(q)) for q in quotes]


@router.get(
    "/stocks",
    response_model=List[TickerResponse],
    tags=["financial"],
    summary="Get stock prices from major exchanges",
)
async def get_stocks():
    from app.services.financial_data import FinancialDataService, financial_service

    quotes = await financial_service.get_stocks()
    return [TickerResponse(**FinancialDataService.quote_to_dict(q)) for q in quotes]


@router.get(
    "/commodities",
    response_model=List[TickerResponse],
    tags=["financial"],
    summary="Get commodity prices",
)
async def get_commodities():
    from app.services.financial_data import FinancialDataService, financial_service

    quotes = await financial_service.get_commodities()
    return [TickerResponse(**FinancialDataService.quote_to_dict(q)) for q in quotes]


@router.get(
    "/indices",
    response_model=List[TickerResponse],
    tags=["financial"],
    summary="Get major market index values",
)
async def get_indices():
    from app.services.financial_data import FinancialDataService, financial_service

    quotes = await financial_service.get_indices()
    return [TickerResponse(**FinancialDataService.quote_to_dict(q)) for q in quotes]


@router.get(
    "/forex",
    response_model=List[TickerResponse],
    tags=["financial"],
    summary="Get foreign exchange rates",
)
async def get_forex():
    from app.services.financial_data import FinancialDataService, financial_service

    quotes = await financial_service.get_forex()
    return [TickerResponse(**FinancialDataService.quote_to_dict(q)) for q in quotes]


@router.get(
    "/summary",
    tags=["financial"],
    summary="Get all market data in one call",
)
async def get_market_summary():
    from app.services.financial_data import FinancialDataService, financial_service

    market = await financial_service.get_market_summary()
    return {
        "indices": [FinancialDataService.quote_to_dict(q) for q in market.indices],
        "stocks": [FinancialDataService.quote_to_dict(q) for q in market.stocks],
        "crypto": [FinancialDataService.quote_to_dict(q) for q in market.crypto],
        "commodities": [
            FinancialDataService.quote_to_dict(q) for q in market.commodities
        ],
        "forex": [FinancialDataService.quote_to_dict(q) for q in market.forex],
        "last_updated": market.last_updated,
    }
