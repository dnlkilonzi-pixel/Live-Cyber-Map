"""REST API routes for the Live Cyber Map backend."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.attack import AttackEventResponse
from app.services.anomaly_detector import anomaly_detector
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Replay state (simple in-memory toggle)
# ---------------------------------------------------------------------------
_replay_state = {"active": False, "speed": 1.0}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["meta"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Return service health including DB and Redis reachability."""
    db_ok = False
    redis_ok = False

    # Check database
    try:
        await db.execute(select(1))
        db_ok = True
    except Exception as exc:
        logger.debug("DB health check failed: %s", exc)

    # Check Redis
    try:
        from app.main import redis_client  # import here to avoid circular refs
        if redis_client is not None:
            await redis_client.ping()
            redis_ok = True
    except Exception as exc:
        logger.debug("Redis health check failed: %s", exc)

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db_ok else "unavailable",
        "redis": "connected" if redis_ok else "unavailable",
        "websocket_connections": ws_manager.get_connection_count(),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", tags=["stats"])
async def get_stats():
    """Return live event rate statistics and anomaly indicators."""
    return {
        "rates": anomaly_detector.get_stats(),
        "top_attackers": anomaly_detector.get_top_attackers(10),
        "top_targets": anomaly_detector.get_top_targets(10),
        "attack_types": anomaly_detector.get_attack_type_stats(),
        "ws_connections": ws_manager.get_connection_count(),
    }


# ---------------------------------------------------------------------------
# Recent attacks (in-memory)
# ---------------------------------------------------------------------------

@router.get("/attacks/recent", tags=["attacks"])
async def get_recent_attacks(
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Return the most recent *limit* attack events from the in-memory buffer."""
    from app.main import processor  # avoid circular import at module level

    if processor is None:
        return {"events": [], "count": 0}

    events = processor.get_recent_events(limit)
    return {"events": events, "count": len(events)}


# ---------------------------------------------------------------------------
# Historical attacks (database)
# ---------------------------------------------------------------------------

@router.get("/attacks/history", tags=["attacks"], response_model=List[AttackEventResponse])
async def get_attack_history(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    attack_type: Optional[str] = Query(default=None),
    source_country: Optional[str] = Query(default=None),
    dest_country: Optional[str] = Query(default=None),
    min_severity: Optional[int] = Query(default=None, ge=1, le=10),
    max_severity: Optional[int] = Query(default=None, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """Return historical attack events from the database with optional filters."""
    from app.models.attack import AttackEvent

    try:
        stmt = select(AttackEvent).order_by(desc(AttackEvent.timestamp))

        if attack_type:
            stmt = stmt.where(AttackEvent.attack_type == attack_type)
        if source_country:
            stmt = stmt.where(AttackEvent.source_country == source_country)
        if dest_country:
            stmt = stmt.where(AttackEvent.dest_country == dest_country)
        if min_severity is not None:
            stmt = stmt.where(AttackEvent.severity >= min_severity)
        if max_severity is not None:
            stmt = stmt.where(AttackEvent.severity <= max_severity)

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return rows
    except Exception as exc:
        logger.warning("DB query failed in /attacks/history: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


# ---------------------------------------------------------------------------
# Replay endpoints
# ---------------------------------------------------------------------------

@router.get("/replay", tags=["replay"])
async def get_replay_status():
    """Return the current replay mode status."""
    return _replay_state


@router.post("/replay/start", tags=["replay"])
async def start_replay(speed: float = Query(default=1.0, gt=0.0, le=10.0)):
    """Activate replay mode at the given speed multiplier."""
    _replay_state["active"] = True
    _replay_state["speed"] = speed
    await ws_manager.broadcast({"type": "replay_started", "speed": speed})
    return {"status": "replay started", "speed": speed}


@router.post("/replay/stop", tags=["replay"])
async def stop_replay():
    """Deactivate replay mode."""
    _replay_state["active"] = False
    _replay_state["speed"] = 1.0
    await ws_manager.broadcast({"type": "replay_stopped"})
    return {"status": "replay stopped"}


@router.post("/replay/seek", tags=["replay"])
async def seek_replay(
    position: int = Query(default=0, ge=0, description="Target event index to jump to"),
):
    """Seek the replay to a specific event index position.

    The frontend scrubber sends this to jump to any point in history.
    Broadcasts a ``replay_seek`` message so all clients can sync their
    UI progress indicator.
    """
    _replay_state["position"] = position
    await ws_manager.broadcast({"type": "replay_seek", "position": position})
    return {"status": "seek", "position": position}


@router.get("/replay/intelligence", tags=["replay"])
async def get_replay_intelligence(
    from_ts: Optional[float] = Query(
        default=None,
        alias="from",
        description="Unix timestamp (seconds). Defaults to 24 hours ago.",
    ),
    to_ts: Optional[float] = Query(
        default=None,
        alias="to",
        description="Unix timestamp (seconds). Defaults to now.",
    ),
    limit: int = Query(default=500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return historical intelligence snapshots for the replay slider.

    Combines:
    - ``country_risk_snapshots`` – risk score timeline
    - ``financial_snapshots`` – price timeline (real quotes only)

    Both are bucketed into the requested time window and returned as a merged
    sorted timeline so the frontend can scrub through them.
    """
    import time as _time

    from app.models.financial import FinancialSnapshot
    from app.models.intelligence import CountryRiskSnapshot

    now = _time.time()
    t_to = datetime.fromtimestamp(to_ts, tz=timezone.utc) if to_ts else datetime.now(timezone.utc)
    t_from = (
        datetime.fromtimestamp(from_ts, tz=timezone.utc)
        if from_ts
        else datetime.fromtimestamp(now - 86400, tz=timezone.utc)
    )

    try:
        # Risk snapshots
        risk_stmt = (
            select(CountryRiskSnapshot)
            .where(
                and_(
                    CountryRiskSnapshot.snapshotted_at >= t_from,
                    CountryRiskSnapshot.snapshotted_at <= t_to,
                )
            )
            .order_by(CountryRiskSnapshot.snapshotted_at)
            .limit(limit)
        )
        risk_rows = (await db.execute(risk_stmt)).scalars().all()

        # Financial snapshots (real data only to keep payload small)
        fin_stmt = (
            select(FinancialSnapshot)
            .where(
                and_(
                    FinancialSnapshot.snapshotted_at >= t_from,
                    FinancialSnapshot.snapshotted_at <= t_to,
                    FinancialSnapshot.is_real.is_(True),
                )
            )
            .order_by(FinancialSnapshot.snapshotted_at)
            .limit(limit)
        )
        fin_rows = (await db.execute(fin_stmt)).scalars().all()

        risk_events = [
            {
                "type": "risk",
                "ts": r.snapshotted_at.timestamp(),
                "iso2": r.iso2,
                "risk_score": round(r.risk_score, 1),
                "cyber_score": round(r.cyber_score, 1),
                "news_score": round(r.news_score, 1),
                "attack_count_24h": r.attack_count_24h,
            }
            for r in risk_rows
        ]

        fin_events = [
            {
                "type": "financial",
                "ts": f.snapshotted_at.timestamp(),
                "symbol": f.symbol,
                "asset_class": f.asset_class,
                "price": f.price,
                "change_pct": round(f.change_pct, 2),
            }
            for f in fin_rows
        ]

        # Merge and sort by timestamp
        merged = sorted(risk_events + fin_events, key=lambda e: e["ts"])

        return {
            "from": t_from.isoformat(),
            "to": t_to.isoformat(),
            "total": len(merged),
            "events": merged,
        }

    except Exception as exc:
        logger.warning("Replay intelligence query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

