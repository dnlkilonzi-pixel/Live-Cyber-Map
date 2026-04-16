"""FastAPI application entry point for the Live Cyber Map backend.

Startup sequence:
  1. Initialise database tables (init_db)
  2. Connect to Redis
  3. Start AttackGenerator → AttackProcessor pipeline
  4. Start WebSocketManager Redis subscriber

Shutdown sequence (reverse):
  1. Stop WebSocketManager subscriber
  2. Stop processor (flush pending DB records)
  3. Stop generator
  4. Close Redis connection
  5. Dispose SQLAlchemy engine
"""

from __future__ import annotations

import asyncio
import logging
import time as _rl_time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine, init_db
from app.services.anomaly_detector import anomaly_detector
from app.services.country_risk import country_risk_service
from app.services.financial_data import financial_service
from app.services.generator import AttackGenerator
from app.services.news_aggregator import news_aggregator
from app.services.ollama_service import ollama_service
from app.services.processor import AttackProcessor
from app.services.websocket_manager import ws_manager
from app.services.alert_service import alert_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level references so routes/handlers can import them at request time
# ---------------------------------------------------------------------------
redis_client: Optional[aioredis.Redis] = None
generator: Optional[AttackGenerator] = None
processor: Optional[AttackProcessor] = None

# ---------------------------------------------------------------------------
# Rate-limiter state (module-level so tests can inspect it)
# ---------------------------------------------------------------------------
_RATE_LIMIT_PATHS = frozenset({"/api/attacks/recent", "/api/intelligence/risk"})
_RATE_WINDOW = 60.0
_RATE_MAX = 60
_rl_counts: dict = defaultdict(list)  # ip -> list[float] of request timestamps


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global redis_client, generator, processor

    # ------------------------------------------------------------------ #
    # STARTUP
    # ------------------------------------------------------------------ #

    # 1. Database
    await init_db()

    # 2. Redis (graceful degradation if unavailable)
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
        )
        await redis_client.ping()
        logger.info("Redis connected at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — running without pub/sub.", exc)
        redis_client = None

    # 3. Wire up generator → queue → processor
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)  # type: ignore[type-arg]
    generator = AttackGenerator(event_queue)
    processor = AttackProcessor(
        queue=event_queue,
        redis_client=redis_client,
        db_session_factory=AsyncSessionLocal,
    )

    await generator.start()
    await processor.start()

    # 4. WebSocket manager — inject Redis and start subscriber
    ws_manager.set_redis(redis_client)
    await ws_manager.start_redis_subscriber()

    # 5. Background task: feed anomaly detector from processor history
    anomaly_task = asyncio.create_task(_anomaly_feed_loop())

    # 6. Intelligence services (graceful – they degrade if external APIs are down)
    news_aggregator.set_redis(redis_client)
    await news_aggregator.start()

    financial_service.set_redis(redis_client)
    await financial_service.start()

    await country_risk_service.start()

    # Non-blocking Ollama probe (result cached for later requests)
    asyncio.create_task(ollama_service.is_available())

    # 7. Background task: feed country risk from attack stream
    risk_task = asyncio.create_task(_risk_feed_loop())

    # 8. Alert service – load rules from DB and start background evaluation
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            from app.models.alert import AlertRule
            result = await session.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
            rules = list(result.scalars().all())
            await alert_service.reload_rules(rules)
        await alert_service.start()
    except Exception as exc:
        logger.warning("Alert service startup error (continuing without alerts): %s", exc)

    logger.info("Global Intelligence Dashboard backend started.")
    yield

    # ------------------------------------------------------------------ #
    # SHUTDOWN
    # ------------------------------------------------------------------ #
    logger.info("Shutting down backend…")

    risk_task.cancel()
    try:
        await risk_task
    except asyncio.CancelledError:
        pass

    anomaly_task.cancel()
    try:
        await anomaly_task
    except asyncio.CancelledError:
        pass

    await news_aggregator.stop()
    await financial_service.stop()
    await country_risk_service.stop()
    await alert_service.stop()
    await ws_manager.stop_redis_subscriber()
    await processor.stop()
    await generator.stop()

    if redis_client:
        await redis_client.aclose()

    await engine.dispose()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Global Intelligence Dashboard API",
        description=(
            "Real-time global intelligence platform. "
            "Aggregates cyber attacks, news, financial data, and geopolitical "
            "risk scores. Streams events over WebSocket and exposes REST endpoints."
        ),
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured logging middleware: injects X-Request-ID and logs every
    # request with method, path, status code, and wall-clock latency.
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = _rl_time.perf_counter()
        response = await call_next(request)
        elapsed_ms = ((_rl_time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = req_id
        logger.info(
            "%s %s %s %.1fms req_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            req_id,
        )
        return response

    # Simple in-memory per-IP rate limiter for expensive REST endpoints.
    # Limit: 60 requests per 60-second window per IP.
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in _RATE_LIMIT_PATHS:
            ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
                request.client.host if request.client else "unknown"
            )
            now = _rl_time.time()
            window_start = now - _RATE_WINDOW
            _rl_counts[ip] = [t for t in _rl_counts[ip] if t > window_start]
            if len(_rl_counts[ip]) >= _RATE_MAX:
                return Response(
                    content='{"detail":"Too many requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(int(_RATE_WINDOW))},
                )
            _rl_counts[ip].append(now)
        return await call_next(request)

    # REST routes
    from app.api.routes import router as api_router
    from app.api.intelligence_routes import router as intel_router
    from app.api.financial_routes import router as financial_router
    from app.api.layers_routes import router as layers_router
    from app.api.alert_routes import router as alert_router

    app.include_router(api_router, prefix="/api")
    app.include_router(intel_router, prefix="/api/intelligence")
    app.include_router(financial_router, prefix="/api/financial")
    app.include_router(layers_router, prefix="/api/layers")
    app.include_router(alert_router, prefix="/api/alerts")

    # WebSocket handler
    from app.websocket.handler import router as ws_router
    app.include_router(ws_router)

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _anomaly_feed_loop() -> None:
    """Periodically snapshot processor history and feed new events to the
    anomaly detector.  This runs at ~10 Hz — fast enough for real-time stats
    but cheap enough not to dominate the event loop.
    """
    last_seen_count = 0
    while True:
        try:
            await asyncio.sleep(0.1)
            if processor is None:
                continue
            events = processor.get_recent_events(settings.MAX_EVENTS_HISTORY)
            new_count = len(events)
            if new_count > last_seen_count:
                for event in events[last_seen_count:]:
                    anomaly_detector.add_event(event)
            # Reset when history wraps (ring buffer eviction)
            if new_count < last_seen_count:
                last_seen_count = 0
            else:
                last_seen_count = new_count
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Anomaly feed error: %s", exc)


async def _risk_feed_loop() -> None:
    """Feed destination-country attack data into the country risk service."""
    last_seen_count = 0
    while True:
        try:
            await asyncio.sleep(1.0)
            if processor is None:
                continue
            events = processor.get_recent_events(settings.MAX_EVENTS_HISTORY)
            new_count = len(events)
            if new_count > last_seen_count:
                for event in events[last_seen_count:]:
                    dest = event.get("dest_country", "")
                    if dest:
                        await country_risk_service.record_attack(dest)
            if new_count < last_seen_count:
                last_seen_count = 0
            else:
                last_seen_count = new_count
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Risk feed error: %s", exc)
