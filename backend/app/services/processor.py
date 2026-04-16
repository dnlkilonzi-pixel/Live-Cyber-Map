"""Attack event processor.

Consumes raw events from the generator queue, enriches them, assigns cluster
IDs, publishes to Redis, and persists to PostgreSQL in batches.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from app.core.config import settings
from app.services.geoip import geoip_service

logger = logging.getLogger(__name__)


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO-8601 timestamp string robustly, handling both 'Z' and '+00:00'."""
    # Python 3.11+ supports 'Z' natively; earlier versions do not
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        # Fallback: replace trailing Z with +00:00 for Python < 3.11
        return datetime.fromisoformat(ts_str.rstrip("Z") + "+00:00")


# Severity bonus per attack type (added to base score)
_SEVERITY_BONUS: Dict[str, int] = {
    "ZeroDay": 3,
    "Ransomware": 2,
    "Intrusion": 1,
    "DDoS": 1,
    "Malware": 1,
    "SQLInjection": 0,
    "BruteForce": -1,
    "Phishing": -1,
    "XSS": -2,
}

# Redis pub/sub channel name
_REDIS_CHANNEL = "attacks"

# Batch size / flush interval for DB persistence
_DB_BATCH_SIZE = 50
_DB_FLUSH_INTERVAL = 2.0  # seconds


class AttackProcessor:
    """Reads from the generator queue, enriches events, and fans out to Redis + DB."""

    def __init__(
        self, queue: asyncio.Queue, redis_client=None, db_session_factory=None
    ) -> None:  # type: ignore[type-arg]
        self._queue = queue
        self._redis = redis_client  # may be None (graceful degradation)
        self._db_factory = db_session_factory  # may be None
        self._running = False
        self._tasks: List[asyncio.Task] = []  # type: ignore[type-arg]
        self._pending_db: List[Dict] = []
        # In-memory ring buffer of recent events for /api/attacks/recent
        self._history: List[Dict] = []
        self._history_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the processing and DB-flush background tasks."""
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._consume_loop()))
        self._tasks.append(asyncio.create_task(self._flush_loop()))
        logger.info("AttackProcessor started.")

    async def stop(self) -> None:
        """Flush pending DB records and stop all background tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        # Final flush
        if self._pending_db:
            await self._flush_to_db()
        logger.info("AttackProcessor stopped.")

    async def process_event(self, event: Dict) -> Dict:
        """Enrich a raw event dict and return the fully-processed version."""
        # Re-enrich source / dest in case geo wasn't set by generator
        if not event.get("source_lat"):
            src_geo = geoip_service.enrich(event["source_ip"])
            event.update(
                {
                    "source_lat": src_geo["lat"],
                    "source_lng": src_geo["lng"],
                    "source_country": src_geo["country"],
                    "source_country_code": src_geo["country_code"],
                }
            )

        if not event.get("dest_lat"):
            dst_geo = geoip_service.enrich(event["dest_ip"])
            event.update(
                {
                    "dest_lat": dst_geo["lat"],
                    "dest_lng": dst_geo["lng"],
                    "dest_country": dst_geo["country"],
                    "dest_country_code": dst_geo["country_code"],
                }
            )

        # Recalculate severity with bonus
        base_severity = event.get("severity", 5)
        bonus = _SEVERITY_BONUS.get(event.get("attack_type", ""), 0)
        event["severity"] = max(1, min(10, base_severity + bonus))

        # Assign cluster: attack_type + source_country_code
        src_code = event.get("source_country_code", "XX")
        event["cluster_id"] = f"{event.get('attack_type', 'Unknown')}:{src_code}"

        # Ensure timestamp is present
        if not event.get("timestamp"):
            event["timestamp"] = datetime.now(timezone.utc).isoformat()

        return event

    def get_recent_events(self, n: int = 100) -> List[Dict]:
        """Return the last *n* events from the in-memory history buffer."""
        return list(self._history[-n:])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """Drain the queue and process each event."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                processed = await self.process_event(event)

                # Broadcast via Redis
                await self._publish_redis(processed)

                # Evaluate alert rules instantly (ATTACK_TYPE + geofence)
                await self._check_alerts(processed)

                # Buffer for DB batch write
                self._pending_db.append(processed)

                # Maintain in-memory history ring buffer
                async with self._history_lock:
                    self._history.append(processed)
                    if len(self._history) > settings.MAX_EVENTS_HISTORY:
                        self._history = self._history[-settings.MAX_EVENTS_HISTORY :]

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error processing event: %s", exc)

    async def _flush_loop(self) -> None:
        """Periodically flush the pending DB buffer."""
        while self._running:
            try:
                await asyncio.sleep(_DB_FLUSH_INTERVAL)
                if self._pending_db:
                    await self._flush_to_db()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in DB flush loop: %s", exc)

    async def _check_alerts(self, event: dict) -> None:
        """Evaluate alert rules against a freshly processed attack event."""
        try:
            from app.services.alert_service import alert_service
            from app.services.websocket_manager import ws_manager

            fired_list = await alert_service.check_attack_event(event)
            for alert in fired_list:
                logger.info("Alert fired: %s", alert.message)
                await ws_manager.broadcast(
                    {
                        "type": "alert",
                        "data": alert.model_dump(),
                    }
                )
        except Exception as exc:
            logger.debug("Alert check error: %s", exc)

    async def _publish_redis(self, event: Dict) -> None:
        """Publish the event to the Redis 'attacks' channel."""
        if self._redis is None:
            return
        try:
            payload = json.dumps(event, default=str)
            await self._redis.publish(_REDIS_CHANNEL, payload)
        except Exception as exc:
            logger.debug("Redis publish failed: %s", exc)

    async def _flush_to_db(self) -> None:
        """Persist buffered events to PostgreSQL and clear the buffer."""
        if not self._db_factory or not self._pending_db:
            self._pending_db.clear()
            return

        batch = list(self._pending_db)
        self._pending_db.clear()

        try:
            from app.models.attack import AttackEvent  # avoid circular import

            async with self._db_factory() as session:
                for ev in batch:
                    ts = ev.get("timestamp")
                    if isinstance(ts, str):
                        ts = _parse_timestamp(ts)
                    row = AttackEvent(
                        source_ip=ev.get("source_ip", "0.0.0.0"),
                        dest_ip=ev.get("dest_ip", "0.0.0.0"),
                        source_country=ev.get("source_country", "Unknown"),
                        dest_country=ev.get("dest_country", "Unknown"),
                        source_lat=float(ev.get("source_lat", 0.0)),
                        source_lng=float(ev.get("source_lng", 0.0)),
                        dest_lat=float(ev.get("dest_lat", 0.0)),
                        dest_lng=float(ev.get("dest_lng", 0.0)),
                        attack_type=ev.get("attack_type", "Unknown"),
                        severity=int(ev.get("severity", 5)),
                        cluster_id=ev.get("cluster_id"),
                        timestamp=ts or datetime.now(timezone.utc),
                    )
                    session.add(row)
                await session.commit()
        except Exception as exc:
            logger.warning("DB flush failed (batch of %d): %s", len(batch), exc)
