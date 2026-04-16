"""Intelligence REST API routes – news, AI briefs, and country risk."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

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
    "/news/by-country/{iso2}",
    response_model=List[NewsItemResponse],
    tags=["intelligence"],
    summary="Get news items tagged for a specific country ISO2 code",
)
async def get_news_by_country(
    iso2: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return news items whose region column matches the given ISO2 country code.

    Falls back to an in-memory name-match on the news aggregator cache if no
    DB rows are found (graceful degradation when DB is unavailable).
    """
    from app.models.intelligence import NewsItemDB

    iso2_upper = iso2.upper()
    try:
        stmt = (
            select(NewsItemDB)
            .where(NewsItemDB.region == iso2_upper)
            .order_by(NewsItemDB.published_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        if rows:
            return [
                NewsItemResponse(
                    id=r.id,
                    title=r.title,
                    summary=r.summary or "",
                    url=r.url,
                    source=r.source,
                    category=r.category,
                    region=r.region,
                    published_at=r.published_at,
                    sentiment_score=r.sentiment_score,
                )
                for r in rows
            ]
    except Exception as exc:
        logger.warning("DB news-by-country query failed for %s: %s", iso2, exc)

    # Fallback: filter in-memory aggregator cache by region or name
    from app.services.news_aggregator import news_aggregator
    from app.services.country_risk import country_risk_service

    country_name = ""
    score = await country_risk_service.get_country_score(iso2_upper)
    if score:
        country_name = score.name

    items = await news_aggregator.get_news(limit=200)
    filtered = [
        i for i in items
        if i.region == iso2_upper
        or (country_name and country_name.lower() in i.title.lower())
    ][:limit]

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
        for i in filtered
    ]


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


@router.post(
    "/ollama/pull",
    tags=["intelligence"],
    summary="Pull a model into the local Ollama instance",
)
async def ollama_pull(model_name: str):
    """Trigger `ollama pull <model_name>`. Returns immediately; the pull runs asynchronously."""
    from app.services.ollama_service import ollama_service
    success = await ollama_service.pull_model(model_name)
    if success:
        await ollama_service.reset_probe()
    return {"status": "pull_initiated" if success else "pull_failed", "model": model_name}


@router.post(
    "/ollama/select",
    tags=["intelligence"],
    summary="Switch the active Ollama model",
)
async def ollama_select_model(model_name: str):
    """Change the active model used for brief generation."""
    from app.services import ollama_service as ollama_module
    ollama_module.OLLAMA_MODEL = model_name
    ollama_module.ollama_service._available = None  # reset probe
    return {"status": "model_changed", "model": model_name}


# ---------------------------------------------------------------------------
# Country risk trend (sparkline data)
# ---------------------------------------------------------------------------

@router.get(
    "/risk/{iso2}/trend",
    tags=["intelligence"],
    summary="24-hour risk score trend for a country",
)
async def get_country_risk_trend(
    iso2: str,
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return hourly risk score snapshots for the past *hours* hours.

    Used by the frontend CountryRiskPanel sparkline chart.
    """
    import time as _time

    from app.models.intelligence import CountryRiskSnapshot

    t_from = datetime.fromtimestamp(
        _time.time() - hours * 3600, tz=timezone.utc
    )

    try:
        stmt = (
            select(CountryRiskSnapshot)
            .where(
                and_(
                    CountryRiskSnapshot.iso2 == iso2.upper(),
                    CountryRiskSnapshot.snapshotted_at >= t_from,
                )
            )
            .order_by(CountryRiskSnapshot.snapshotted_at)
        )
        rows = (await db.execute(stmt)).scalars().all()

        points = [
            {
                "ts": r.snapshotted_at.timestamp(),
                "risk_score": round(r.risk_score, 1),
                "cyber_score": round(r.cyber_score, 1),
                "news_score": round(r.news_score, 1),
                "attack_count_24h": r.attack_count_24h,
            }
            for r in rows
        ]

        return {
            "iso2": iso2.upper(),
            "hours": hours,
            "count": len(points),
            "points": points,
        }

    except Exception as exc:
        logger.warning("Risk trend query failed for %s: %s", iso2, exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


# ---------------------------------------------------------------------------
# Sentiment timeline
# ---------------------------------------------------------------------------

class SentimentPoint(BaseModel):
    ts: float
    sentiment: float
    count: int


@router.get(
    "/sentiment/timeline",
    response_model=List[SentimentPoint],
    tags=["intelligence"],
    summary="Hourly sentiment score timeline for recent news",
)
async def get_sentiment_timeline(
    region: Optional[str] = Query(default=None, description="Filter by region (e.g. 'global', 'europe')"),
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> List[SentimentPoint]:
    """Return hourly average sentiment scores for the past *hours* hours.

    Each bucket represents one hour, with the average sentiment of all news
    published in that window.  Used by the IntelligenceBriefPanel sparkline.
    """
    import time as _time

    from sqlalchemy import func, text

    from app.models.intelligence import NewsItemDB

    t_from = _time.time() - hours * 3600

    try:
        conditions = [NewsItemDB.published_at >= t_from]
        if region:
            conditions.append(NewsItemDB.region == region)

        stmt = (
            select(
                # Floor the published_at float to the nearest hour bucket
                (func.floor(NewsItemDB.published_at / 3600) * 3600).label("bucket"),
                func.avg(NewsItemDB.sentiment_score).label("avg_sentiment"),
                func.count(NewsItemDB.id).label("item_count"),
            )
            .where(and_(*conditions))
            .group_by(text("bucket"))
            .order_by(text("bucket"))
        )
        rows = (await db.execute(stmt)).all()

        return [
            SentimentPoint(
                ts=float(row.bucket),
                sentiment=round(float(row.avg_sentiment), 4),
                count=int(row.item_count),
            )
            for row in rows
        ]

    except Exception as exc:
        logger.warning("Sentiment timeline query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
