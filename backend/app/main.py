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
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine, init_db
from app.services.anomaly_detector import anomaly_detector
from app.services.generator import AttackGenerator
from app.services.processor import AttackProcessor
from app.services.websocket_manager import ws_manager

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

    logger.info("Live Cyber Map backend started.")
    yield

    # ------------------------------------------------------------------ #
    # SHUTDOWN
    # ------------------------------------------------------------------ #
    logger.info("Shutting down Live Cyber Map backend…")

    anomaly_task.cancel()
    try:
        await anomaly_task
    except asyncio.CancelledError:
        pass

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
        title="Live Cyber Map API",
        description=(
            "Real-time global cyber attack visualization platform. "
            "Streams synthetic attack events over WebSocket and exposes "
            "REST endpoints for stats and history."
        ),
        version="1.0.0",
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

    # REST routes
    from app.api.routes import router as api_router
    app.include_router(api_router, prefix="/api")

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
