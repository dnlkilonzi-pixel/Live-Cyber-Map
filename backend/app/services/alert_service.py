"""Alert rule evaluation service.

Evaluates user-defined alert rules against live data and broadcasts
fired alerts over WebSocket so the frontend can display notifications.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from app.models.alert import AlertFired, AlertRule

logger = logging.getLogger(__name__)


class AlertService:
    """Evaluates alert rules in the background and emits notifications."""

    CHECK_INTERVAL = 15  # seconds

    def __init__(self) -> None:
        self._rules: List[AlertRule] = []
        self._lock = asyncio.Lock()
        self._check_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._last_fired: Dict[int, float] = {}  # rule_id -> timestamp of last fire
        self._cooldown = 60.0  # minimum seconds between repeat alerts for the same rule

    async def start(self) -> None:
        self._check_task = asyncio.create_task(self._background_check())
        logger.info("AlertService started")

    async def stop(self) -> None:
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Rule management (in-memory cache; source of truth is DB)
    # ------------------------------------------------------------------

    async def reload_rules(self, rules: List[AlertRule]) -> None:
        async with self._lock:
            self._rules = list(rules)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def check_attack_event(self, event: dict) -> List[AlertFired]:
        """Evaluate ATTACK_TYPE and geofence rules against a live attack event.

        Called directly from the AttackProcessor so alerts fire instantly.
        Also evaluates BBOX (geofence) rules if the event has dest coordinates.
        """
        attack_type = event.get("attack_type", "")
        dest_country = event.get("dest_country", "")
        dest_lat = event.get("dest_lat")
        dest_lng = event.get("dest_lng")

        fired: List[AlertFired] = []
        async with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue

                # ATTACK_TYPE rule
                if rule.condition == "attack_type":
                    if rule.target and rule.target != attack_type:
                        continue
                    if self._is_cooled_down(rule.id):
                        fired.append(AlertFired(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            condition=rule.condition,
                            message=f"{attack_type} attack detected targeting {dest_country}",
                            fired_at=time.time(),
                        ))
                        self._last_fired[rule.id] = time.time()

                # BBOX (geofence) rule
                elif rule.condition == "bbox" and dest_lat is not None and dest_lng is not None:
                    if rule.bbox and self._point_in_bbox(float(dest_lat), float(dest_lng), rule.bbox):
                        if self._is_cooled_down(rule.id):
                            fired.append(AlertFired(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                condition=rule.condition,
                                message=(
                                    f"{attack_type} attack targeted {dest_country} "
                                    f"within geofence ({dest_lat:.2f}, {dest_lng:.2f})"
                                ),
                                fired_at=time.time(),
                            ))
                            self._last_fired[rule.id] = time.time()

        return fired

    @staticmethod
    def _point_in_bbox(lat: float, lng: float, bbox: str) -> bool:
        """Return True if (lat, lng) is inside the bbox string 'lat_min,lng_min,lat_max,lng_max'."""
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                return False
            lat_min, lng_min, lat_max, lng_max = parts
            return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max
        except (ValueError, AttributeError):
            return False

    async def check_country_risk(self, iso2: str, risk_score: float) -> List[AlertFired]:
        """Check RISK_ABOVE rules for a given country."""
        fired: List[AlertFired] = []
        async with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.condition != "risk_above":
                    continue
                if rule.target and rule.target.upper() != iso2.upper():
                    continue
                if rule.threshold is None:
                    continue
                if risk_score > rule.threshold:
                    if self._is_cooled_down(rule.id):
                        fired.append(AlertFired(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            condition=rule.condition,
                            message=f"Risk score for {iso2} is {risk_score:.0f} (threshold: {rule.threshold:.0f})",
                            fired_at=time.time(),
                        ))
                        self._last_fired[rule.id] = time.time()
        return fired

    async def check_attack(self, attack_type: str, dest_country: str) -> List[AlertFired]:
        """Check ATTACK_TYPE rules."""
        fired: List[AlertFired] = []
        async with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.condition != "attack_type":
                    continue
                if rule.target and rule.target != attack_type:
                    continue
                if self._is_cooled_down(rule.id):
                    fired.append(AlertFired(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        condition=rule.condition,
                        message=f"{attack_type} attack detected targeting {dest_country}",
                        fired_at=time.time(),
                    ))
                    self._last_fired[rule.id] = time.time()
        return fired

    async def check_price_change(self, symbol: str, change_pct: float) -> List[AlertFired]:
        """Check PRICE_CHANGE rules."""
        fired: List[AlertFired] = []
        async with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.condition != "price_change":
                    continue
                if rule.target and rule.target.upper() != symbol.upper():
                    continue
                if rule.threshold is None:
                    continue
                if abs(change_pct) > abs(rule.threshold):
                    direction = "up" if change_pct > 0 else "down"
                    if self._is_cooled_down(rule.id):
                        fired.append(AlertFired(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            condition=rule.condition,
                            message=f"{symbol} moved {direction} {abs(change_pct):.2f}% (threshold: {abs(rule.threshold):.1f}%)",
                            fired_at=time.time(),
                        ))
                        self._last_fired[rule.id] = time.time()
        return fired

    async def check_anomaly_score(self, score: float) -> List[AlertFired]:
        """Check ANOMALY_SCORE rules against the current anomaly score."""
        fired: List[AlertFired] = []
        async with self._lock:
            for rule in self._rules:
                if not rule.enabled:
                    continue
                if rule.condition != "anomaly_score":
                    continue
                if rule.threshold is None:
                    continue
                if score > rule.threshold:
                    if self._is_cooled_down(rule.id):
                        fired.append(AlertFired(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            condition=rule.condition,
                            message=f"Anomaly score {score:.2f} exceeded threshold {rule.threshold:.2f}",
                            fired_at=time.time(),
                        ))
                        self._last_fired[rule.id] = time.time()
        return fired

    def _is_cooled_down(self, rule_id: int) -> bool:
        last = self._last_fired.get(rule_id, 0.0)
        return (time.time() - last) >= self._cooldown

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _background_check(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
                await self._run_periodic_checks()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("AlertService check error: %s", exc)

    async def _run_periodic_checks(self) -> None:
        """Run country risk and anomaly score checks periodically."""
        from app.services.anomaly_detector import anomaly_detector
        from app.services.country_risk import country_risk_service
        from app.services.websocket_manager import ws_manager

        scores = await country_risk_service.get_all_scores()
        for score in scores:
            fired_list = await self.check_country_risk(score.iso2, score.risk_score)
            for alert in fired_list:
                logger.info("Alert fired: %s", alert.message)
                await ws_manager.broadcast({
                    "type": "alert",
                    "data": alert.model_dump(),
                })

        # Check anomaly score rules
        stats = anomaly_detector.get_stats()
        anomaly_fired = await self.check_anomaly_score(stats.get("anomaly_score", 0.0))
        for alert in anomaly_fired:
            logger.info("Anomaly alert fired: %s", alert.message)
            await ws_manager.broadcast({
                "type": "alert",
                "data": alert.model_dump(),
            })


# Module-level singleton
alert_service = AlertService()
