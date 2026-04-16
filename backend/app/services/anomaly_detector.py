"""Anomaly detector service.

Maintains sliding-window statistics over the event stream and detects
rate spikes, top attackers, top targets, and per-type counts.
"""

from __future__ import annotations

import logging
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

# Sliding window duration in seconds
_WINDOW_SECONDS = 60
# Number of recent second-buckets to use for the rolling average
_ROLLING_BUCKETS = 10


class AnomalyDetector:
    """Tracks live event statistics and emits anomaly signals.

    All state is kept in-memory.  Thread/task-safety is achieved by the GIL
    and the single-threaded asyncio event loop — no explicit locking needed.
    """

    def __init__(self) -> None:
        # Each entry: (timestamp_float, event_dict)
        self._window: deque = deque()

        # Running counters (not evicted with the window — all-time totals)
        self._attacker_counter: Counter = Counter()  # key: source_ip
        self._attacker_country: Dict[str, str] = {}  # source_ip → country
        self._target_counter: Counter = Counter()  # key: dest_country
        self._type_counter: Counter = Counter()  # key: attack_type

        # Per-second buckets for rolling-average calculation
        # deque of ints, each representing count in that second
        self._second_buckets: deque = deque(maxlen=_WINDOW_SECONDS)
        self._current_second: int = 0
        self._current_bucket_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_event(self, event: Dict) -> None:
        """Record *event* in all tracking structures."""
        now = datetime.now(timezone.utc).timestamp()

        # Sliding window maintenance
        self._window.append((now, event))
        self._evict_old(now)

        # Update per-second bucket
        current_second = int(now)
        if current_second != self._current_second:
            # Flush previous second bucket
            self._second_buckets.append(self._current_bucket_count)
            # Fill any gap seconds with 0
            gap = current_second - self._current_second - 1
            self._second_buckets.extend([0] * min(gap, _WINDOW_SECONDS))
            self._current_second = current_second
            self._current_bucket_count = 0
        self._current_bucket_count += 1

        # Update counters
        src_ip = event.get("source_ip", "0.0.0.0")
        self._attacker_counter[src_ip] += 1
        if src_ip not in self._attacker_country:
            self._attacker_country[src_ip] = event.get("source_country", "Unknown")

        self._target_counter[event.get("dest_country", "Unknown")] += 1
        self._type_counter[event.get("attack_type", "Unknown")] += 1

    def get_stats(self) -> Dict:
        """Return current rate statistics and anomaly indicators."""
        now = datetime.now(timezone.utc).timestamp()
        self._evict_old(now)

        window_count = len(self._window)
        events_per_second = window_count / _WINDOW_SECONDS if self._window else 0.0

        # Rolling average over last _ROLLING_BUCKETS completed seconds
        recent_buckets = list(self._second_buckets)[-_ROLLING_BUCKETS:]
        rolling_avg = (
            sum(recent_buckets) / len(recent_buckets) if recent_buckets else 0.0
        )

        # Current-second rate (live bucket)
        current_rate = self._current_bucket_count  # events in this second so far

        # Anomaly: current rate > 2× rolling average (with a minimum threshold)
        is_anomaly = (rolling_avg > 0) and (current_rate > rolling_avg * 2.0)
        anomaly_score = (
            round((current_rate / rolling_avg) - 1.0, 2) if rolling_avg > 0 else 0.0
        )

        return {
            "events_per_second": round(events_per_second, 2),
            "current_rate": current_rate,
            "rolling_avg": round(rolling_avg, 2),
            "window_size_seconds": _WINDOW_SECONDS,
            "total_events_in_window": window_count,
            "is_anomaly": is_anomaly,
            "anomaly_score": max(0.0, anomaly_score),
        }

    def get_top_attackers(self, n: int = 10) -> List[Dict]:
        """Return the top *n* source IPs by event count."""
        return [
            {
                "ip": ip,
                "country": self._attacker_country.get(ip, "Unknown"),
                "count": count,
            }
            for ip, count in self._attacker_counter.most_common(n)
        ]

    def get_top_targets(self, n: int = 10) -> List[Dict]:
        """Return the top *n* destination countries by event count."""
        return [
            {"country": country, "count": count}
            for country, count in self._target_counter.most_common(n)
        ]

    def get_attack_type_stats(self) -> Dict[str, int]:
        """Return a mapping of attack_type → total event count."""
        return dict(self._type_counter)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_old(self, now: float) -> None:
        """Remove events outside the sliding window."""
        cutoff = now - _WINDOW_SECONDS
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()


# Module-level singleton
anomaly_detector = AnomalyDetector()
