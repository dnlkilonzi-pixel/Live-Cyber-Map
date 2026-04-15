"""Intelligence REST API routes – news, AI briefs, and country risk."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class NewsItemResponse(BaseModel):
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: str
    region: str
    published_at: float
    sentiment_score: float

    model_config = {"from_attributes": True}


class BriefRequest(BaseModel):
    category: str = "world"
    region: Optional[str] = None
    limit: int = 15
    style: str = "intelligence analyst"


class BriefResponse(BaseModel):
    brief: str
    source_count: int
    category: str
    ai_generated: bool


class CountryRiskResponse(BaseModel):
    iso2: str
    iso3: str
    name: str
    risk_score: float
    cyber_score: float
    news_score: float
    stability_baseline: float
    attack_count_24h: int
    lat: float
    lng: float
    last_updated: float


class OllamaStatusResponse(BaseModel):
    available: bool
    models: list


# ---------------------------------------------------------------------------
# News endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/news",
    response_model=List[NewsItemResponse],
    tags=["intelligence"],
    summary="Get aggregated news headlines",
)
async def get_news(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    region: Optional[str] = Query(default=None, description="Filter by region"),
    limit: int = Query(default=30, ge=1, le=200),
):
    """Return recent news headlines aggregated from 40+ RSS feeds."""
    from app.services.news_aggregator import news_aggregator

    items = await news_aggregator.get_news(
        category=category, limit=limit, region=region
    )
    return [
        NewsItemResponse(
            id=i.id,
            title=i.title,
            summary=i.summary,
            url=i.url,
            source=i.source,
            category=i.category,
            region=i.region,
            published_at=i.published_at,
            sentiment_score=i.sentiment_score,
        )
        for i in items
    ]


@router.get(
    "/news/categories",
    tags=["intelligence"],
    summary="List available news categories",
)
async def get_categories():
    from app.services.news_aggregator import news_aggregator
    return {"categories": await news_aggregator.get_categories()}


# ---------------------------------------------------------------------------
# AI Brief endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/brief",
    response_model=BriefResponse,
    tags=["intelligence"],
    summary="Generate an AI-synthesized intelligence brief",
)
async def generate_brief(body: BriefRequest):
    """Use the local Ollama model to synthesize a brief from recent headlines."""
    from app.services.news_aggregator import news_aggregator
    from app.services.ollama_service import ollama_service

    items = await news_aggregator.get_news(
        category=body.category, limit=body.limit, region=body.region
    )
    if not items:
        return BriefResponse(
            brief=f"No recent news available for category: {body.category}.",
            source_count=0,
            category=body.category,
            ai_generated=False,
        )

    headlines = [i.title for i in items]
    ai_available = await ollama_service.is_available()

    brief = await ollama_service.generate_brief(
        headlines=headlines,
        context=f"{body.category} news",
        style=body.style,
    )

    return BriefResponse(
        brief=brief,
        source_count=len(items),
        category=body.category,
        ai_generated=ai_available,
    )


@router.get(
    "/brief/{category}",
    response_model=BriefResponse,
    tags=["intelligence"],
    summary="Get a pre-generated brief for a category",
)
async def get_brief(category: str, limit: int = Query(default=15, ge=3, le=50)):
    from app.services.news_aggregator import news_aggregator
    from app.services.ollama_service import ollama_service

    items = await news_aggregator.get_news(category=category, limit=limit)
    headlines = [i.title for i in items]
    ai_available = await ollama_service.is_available()

    brief = await ollama_service.generate_brief(
        headlines=headlines,
        context=f"{category} world events",
    )

    return BriefResponse(
        brief=brief,
        source_count=len(items),
        category=category,
        ai_generated=ai_available,
    )


# ---------------------------------------------------------------------------
# Country risk endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/risk",
    response_model=List[CountryRiskResponse],
    tags=["intelligence"],
    summary="Get risk scores for all tracked countries",
)
async def get_all_risk_scores():
    from app.services.country_risk import country_risk_service

    scores = await country_risk_service.get_all_scores()
    return [
        CountryRiskResponse(
            iso2=s.iso2, iso3=s.iso3, name=s.name,
            risk_score=s.risk_score, cyber_score=s.cyber_score,
            news_score=s.news_score, stability_baseline=s.stability_baseline,
            attack_count_24h=s.attack_count_24h,
            lat=s.lat, lng=s.lng, last_updated=s.last_updated,
        )
        for s in scores
    ]


@router.get(
    "/risk/{iso2}",
    response_model=CountryRiskResponse,
    tags=["intelligence"],
    summary="Get risk score for a specific country",
)
async def get_country_risk(iso2: str):
    from app.services.country_risk import country_risk_service

    score = await country_risk_service.get_country_score(iso2.upper())
    if not score:
        raise HTTPException(status_code=404, detail=f"Country '{iso2}' not found")
    return CountryRiskResponse(
        iso2=score.iso2, iso3=score.iso3, name=score.name,
        risk_score=score.risk_score, cyber_score=score.cyber_score,
        news_score=score.news_score, stability_baseline=score.stability_baseline,
        attack_count_24h=score.attack_count_24h,
        lat=score.lat, lng=score.lng, last_updated=score.last_updated,
    )


# ---------------------------------------------------------------------------
# Ollama status
# ---------------------------------------------------------------------------

@router.get(
    "/ollama/status",
    response_model=OllamaStatusResponse,
    tags=["intelligence"],
    summary="Check Ollama AI availability",
)
async def ollama_status():
    from app.services.ollama_service import ollama_service

    available = await ollama_service.is_available()
    models = await ollama_service.list_models() if available else []
    return OllamaStatusResponse(available=available, models=models)


@router.post(
    "/ollama/reset",
    tags=["intelligence"],
    summary="Reset Ollama availability probe",
)
async def ollama_reset():
    from app.services.ollama_service import ollama_service
    await ollama_service.reset_probe()
    return {"status": "probe reset"}
