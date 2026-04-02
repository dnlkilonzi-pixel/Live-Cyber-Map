"""Attack event generator.

Produces simulated cyber attack events at the configured rate and pushes
them onto an asyncio.Queue for downstream processing.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.geoip import geoip_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attack type weights  (higher = more frequent)
# ---------------------------------------------------------------------------
_ATTACK_TYPES_WEIGHTED: List[Tuple[str, int]] = [
    ("DDoS", 25),
    ("BruteForce", 20),
    ("Malware", 15),
    ("Phishing", 12),
    ("SQLInjection", 10),
    ("Intrusion", 8),
    ("XSS", 5),
    ("Ransomware", 4),
    ("ZeroDay", 1),
]

_ATTACK_TYPES, _ATTACK_WEIGHTS = zip(*_ATTACK_TYPES_WEIGHTED)

# ---------------------------------------------------------------------------
# Source country weights (known hostile actors appear more often)
# ---------------------------------------------------------------------------
_SOURCE_COUNTRIES_WEIGHTED: List[Tuple[str, int]] = [
    ("CN", 25),  # China
    ("RU", 22),  # Russia
    ("US", 10),  # United States (also used offensively in simulations)
    ("IR", 8),   # Iran
    ("KP", 6),   # North Korea
    ("UA", 5),
    ("BR", 4),
    ("IN", 4),
    ("DE", 3),
    ("NG", 3),
    ("RO", 3),
    ("PK", 2),
    ("TR", 2),
    ("VN", 2),
    ("ID", 1),
]

# ---------------------------------------------------------------------------
# Target country weights (popular targets appear more often)
# ---------------------------------------------------------------------------
_TARGET_COUNTRIES_WEIGHTED: List[Tuple[str, int]] = [
    ("US", 28),
    ("GB", 12),
    ("DE", 10),
    ("FR", 9),
    ("IL", 8),
    ("AU", 6),
    ("JP", 5),
    ("CA", 5),
    ("KR", 4),
    ("NL", 4),
    ("UA", 3),
    ("IN", 3),
    ("TW", 3),
]

_SRC_CODES, _SRC_WEIGHTS = zip(*_SOURCE_COUNTRIES_WEIGHTED)
_DST_CODES, _DST_WEIGHTS = zip(*_TARGET_COUNTRIES_WEIGHTED)


class AttackGenerator:
    """Generates synthetic attack events and places them on an asyncio.Queue."""

    def __init__(self, queue: asyncio.Queue) -> None:  # type: ignore[type-arg]
        self._queue = queue
        self._running = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_event(self) -> Dict:
        """Create a single realistic attack event dict."""
        src_code = random.choices(_SRC_CODES, weights=_SRC_WEIGHTS, k=1)[0]
        # Ensure source ≠ destination
        dst_candidates = [c for c in _DST_CODES if c != src_code]
        dst_weights = [
            w for c, w in _TARGET_COUNTRIES_WEIGHTED if c != src_code
        ]
        if not dst_weights:
            dst_weights = [1] * len(dst_candidates)
        dst_code = random.choices(dst_candidates, weights=dst_weights, k=1)[0]

        src_ip = geoip_service.get_random_ip_for_country(src_code)
        dst_ip = geoip_service.get_random_ip_for_country(dst_code)

        src_geo = geoip_service.enrich(src_ip)
        dst_geo = geoip_service.enrich(dst_ip)

        attack_type = random.choices(_ATTACK_TYPES, weights=_ATTACK_WEIGHTS, k=1)[0]

        # Severity: ZeroDay and Ransomware skew high; BruteForce / XSS skew lower
        severity = self._generate_severity(attack_type)

        return {
            "id": str(uuid.uuid4()),
            "source_ip": src_ip,
            "dest_ip": dst_ip,
            "source_country": src_geo["country"],
            "source_country_code": src_geo["country_code"],
            "dest_country": dst_geo["country"],
            "dest_country_code": dst_geo["country_code"],
            "source_lat": src_geo["lat"],
            "source_lng": src_geo["lng"],
            "dest_lat": dst_geo["lat"],
            "dest_lng": dst_geo["lng"],
            "attack_type": attack_type,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cluster_id": None,  # assigned later by processor
        }

    async def start(self) -> None:
        """Start the background generation loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("AttackGenerator started at %d events/s", settings.EVENTS_PER_SECOND)

    async def stop(self) -> None:
        """Stop the generation loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AttackGenerator stopped.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Continuously generate events at the configured rate."""
        interval = 1.0 / max(settings.EVENTS_PER_SECOND, 1)
        while self._running:
            try:
                event = await self.generate_event()
                # Non-blocking put; drop if queue is full to avoid memory growth
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.debug("Generator queue full — dropping event.")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in generator loop: %s", exc)
                await asyncio.sleep(1)

    @staticmethod
    def _generate_severity(attack_type: str) -> int:
        """Return a severity score (1-10) biased by attack type."""
        high_severity_types = {"ZeroDay", "Ransomware", "Intrusion"}
        low_severity_types = {"XSS", "Phishing", "BruteForce"}

        if attack_type in high_severity_types:
            return random.randint(6, 10)
        if attack_type in low_severity_types:
            return random.randint(1, 6)
        return random.randint(3, 8)
