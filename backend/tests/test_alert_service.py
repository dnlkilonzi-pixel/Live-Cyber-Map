"""Unit tests for AlertService.check_anomaly_score and attack-feed pagination.

These tests run entirely in-process and do not require Redis, PostgreSQL, or
any other external service.
"""

from __future__ import annotations

import math
import time
from types import SimpleNamespace

import pytest

from app.services.alert_service import AlertService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: int,
    condition: str = "anomaly_score",
    threshold: float | None = 0.5,
    enabled: bool = True,
    target: str | None = None,
) -> SimpleNamespace:
    """Return a lightweight stub that duck-types AlertRule for the service."""
    return SimpleNamespace(
        id=rule_id,
        name=f"Rule {rule_id}",
        condition=condition,
        threshold=threshold,
        target=target,
        bbox=None,
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# check_anomaly_score
# ---------------------------------------------------------------------------


class TestCheckAnomalyScore:
    """Tests for AlertService.check_anomaly_score."""

    @pytest.mark.anyio
    async def test_fires_when_score_exceeds_threshold(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=0.5)])
        fired = await svc.check_anomaly_score(0.9)
        assert len(fired) == 1
        assert fired[0].rule_id == 1
        assert fired[0].condition == "anomaly_score"
        assert "0.90" in fired[0].message
        assert "0.50" in fired[0].message

    @pytest.mark.anyio
    async def test_does_not_fire_when_score_equals_threshold(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=0.5)])
        fired = await svc.check_anomaly_score(0.5)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_does_not_fire_when_score_below_threshold(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=0.5)])
        fired = await svc.check_anomaly_score(0.3)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_does_not_fire_for_disabled_rule(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=0.5, enabled=False)])
        fired = await svc.check_anomaly_score(1.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_does_not_fire_when_threshold_is_none(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=None)])
        fired = await svc.check_anomaly_score(1.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_does_not_fire_for_wrong_condition(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, condition="risk_above", threshold=0.5)])
        fired = await svc.check_anomaly_score(1.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_fires_multiple_rules_independently(self):
        svc = AlertService()
        await svc.reload_rules(
            [
                _make_rule(1, threshold=0.5),
                _make_rule(2, threshold=0.8),
            ]
        )
        # score=0.7: only rule 1 (threshold 0.5) should fire
        fired_one = await svc.check_anomaly_score(0.7)
        assert len(fired_one) == 1
        assert fired_one[0].rule_id == 1

        # Fresh service to avoid cooldown interference
        svc2 = AlertService()
        await svc2.reload_rules(
            [
                _make_rule(1, threshold=0.5),
                _make_rule(2, threshold=0.8),
            ]
        )
        # score=0.9: both rules should fire
        fired_both = await svc2.check_anomaly_score(0.9)
        assert len(fired_both) == 2
        rule_ids = {a.rule_id for a in fired_both}
        assert rule_ids == {1, 2}

    @pytest.mark.anyio
    async def test_cooldown_prevents_duplicate_alerts(self):
        svc = AlertService()
        svc._cooldown = 3600.0  # 1 hour — should not re-fire within this test
        await svc.reload_rules([_make_rule(1, threshold=0.5)])

        # First call fires
        fired1 = await svc.check_anomaly_score(1.0)
        assert len(fired1) == 1

        # Immediate second call is suppressed by the cooldown
        fired2 = await svc.check_anomaly_score(1.0)
        assert len(fired2) == 0

    @pytest.mark.anyio
    async def test_fires_again_after_cooldown_expires(self):
        svc = AlertService()
        svc._cooldown = 0.05  # 50 ms
        await svc.reload_rules([_make_rule(1, threshold=0.5)])

        fired1 = await svc.check_anomaly_score(1.0)
        assert len(fired1) == 1

        # Backdate last_fired to simulate cooldown expiry
        svc._last_fired[1] = time.time() - 1.0

        fired2 = await svc.check_anomaly_score(1.0)
        assert len(fired2) == 1

    @pytest.mark.anyio
    async def test_zero_score_never_fires(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=0.0)])
        # threshold=0.0 means score > 0.0 fires; score == 0.0 should NOT fire
        fired = await svc.check_anomaly_score(0.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_message_format(self):
        svc = AlertService()
        await svc.reload_rules([_make_rule(1, threshold=1.5)])
        fired = await svc.check_anomaly_score(2.75)
        assert len(fired) == 1
        assert "2.75" in fired[0].message
        assert "1.50" in fired[0].message

    @pytest.mark.anyio
    async def test_empty_rules_returns_empty_list(self):
        svc = AlertService()
        await svc.reload_rules([])
        fired = await svc.check_anomaly_score(100.0)
        assert fired == []


# ---------------------------------------------------------------------------
# Attack-feed pagination logic (pure Python, no HTTP)
# ---------------------------------------------------------------------------


class TestAttackFeedPagination:
    """Verify the pagination arithmetic used by GET /api/attacks/recent.

    The endpoint slices a ring-buffer; we test the logic in isolation here
    so we don't need to spin up the full app.
    """

    PAGE_SIZE = 20

    def _paginate(self, total: int, page: int) -> tuple[int, int, int]:
        """Return (total_pages, page_start, page_end) for a given total & page."""
        total_pages = max(1, math.ceil(total / self.PAGE_SIZE))
        safe_page = min(page, total_pages - 1)
        start = safe_page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return total_pages, start, end

    def test_first_page_starts_at_zero(self):
        _, start, _ = self._paginate(total=50, page=0)
        assert start == 0

    def test_first_page_ends_at_page_size(self):
        _, _, end = self._paginate(total=50, page=0)
        assert end == self.PAGE_SIZE

    def test_second_page_starts_at_page_size(self):
        _, start, _ = self._paginate(total=50, page=1)
        assert start == self.PAGE_SIZE

    def test_total_pages_rounds_up(self):
        total_pages, _, _ = self._paginate(total=21, page=0)
        assert total_pages == 2

    def test_total_pages_exact_multiple(self):
        total_pages, _, _ = self._paginate(total=40, page=0)
        assert total_pages == 2

    def test_page_clamped_when_out_of_range(self):
        # Requesting page 999 with only 50 items should give the last page
        total_pages, start, _ = self._paginate(total=50, page=999)
        assert total_pages == 3
        # Last page index is 2, start = 40
        assert start == 40

    def test_empty_list_gives_single_page(self):
        total_pages, start, end = self._paginate(total=0, page=0)
        assert total_pages == 1
        assert start == 0
        assert end == self.PAGE_SIZE

    def test_exactly_one_page(self):
        total_pages, start, end = self._paginate(total=self.PAGE_SIZE, page=0)
        assert total_pages == 1
        assert start == 0
        assert end == self.PAGE_SIZE

    def test_page_one_beyond_last_is_clamped(self):
        # total=40 → 2 pages (0 and 1); requesting page 2 should clamp to 1
        total_pages, start, _ = self._paginate(total=40, page=2)
        assert total_pages == 2
        assert start == self.PAGE_SIZE  # page 1


# ---------------------------------------------------------------------------
# AlertService.check_country_risk (bonus coverage)
# ---------------------------------------------------------------------------


class TestCheckCountryRisk:
    """Spot-check the country-risk alert path."""

    @pytest.mark.anyio
    async def test_fires_when_risk_exceeds_threshold(self):
        svc = AlertService()
        rule = _make_rule(10, condition="risk_above", threshold=70.0)
        rule.target = "RU"
        await svc.reload_rules([rule])
        fired = await svc.check_country_risk("RU", 85.0)
        assert len(fired) == 1
        assert "85" in fired[0].message

    @pytest.mark.anyio
    async def test_does_not_fire_below_threshold(self):
        svc = AlertService()
        rule = _make_rule(10, condition="risk_above", threshold=70.0)
        rule.target = "RU"
        await svc.reload_rules([rule])
        fired = await svc.check_country_risk("RU", 60.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_wrong_country_does_not_fire(self):
        svc = AlertService()
        rule = _make_rule(10, condition="risk_above", threshold=70.0)
        rule.target = "RU"
        await svc.reload_rules([rule])
        fired = await svc.check_country_risk("CN", 99.0)
        assert len(fired) == 0


# ---------------------------------------------------------------------------
# AlertService.check_attack (ATTACK_TYPE condition, by type filter)
# ---------------------------------------------------------------------------


class TestCheckAttack:
    """Tests for AlertService.check_attack — standalone method."""

    @pytest.mark.anyio
    async def test_fires_for_matching_target(self):
        svc = AlertService()
        rule = _make_rule(1, condition="attack_type", target="DDoS")
        await svc.reload_rules([rule])
        fired = await svc.check_attack("DDoS", "US")
        assert len(fired) == 1
        assert "DDoS" in fired[0].message

    @pytest.mark.anyio
    async def test_does_not_fire_for_wrong_type(self):
        svc = AlertService()
        rule = _make_rule(1, condition="attack_type", target="Ransomware")
        await svc.reload_rules([rule])
        fired = await svc.check_attack("DDoS", "US")
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_fires_for_any_type_when_no_target(self):
        svc = AlertService()
        rule = _make_rule(1, condition="attack_type", target=None)
        await svc.reload_rules([rule])
        fired = await svc.check_attack("Malware", "DE")
        assert len(fired) == 1

    @pytest.mark.anyio
    async def test_disabled_rule_does_not_fire(self):
        svc = AlertService()
        rule = _make_rule(1, condition="attack_type", target=None, enabled=False)
        await svc.reload_rules([rule])
        fired = await svc.check_attack("DDoS", "US")
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_wrong_condition_does_not_fire(self):
        svc = AlertService()
        rule = _make_rule(1, condition="risk_above", target="DDoS")
        await svc.reload_rules([rule])
        fired = await svc.check_attack("DDoS", "US")
        assert len(fired) == 0


# ---------------------------------------------------------------------------
# AlertService.check_price_change
# ---------------------------------------------------------------------------


class TestCheckPriceChange:
    """Tests for AlertService.check_price_change."""

    @pytest.mark.anyio
    async def test_fires_when_change_exceeds_threshold(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=5.0, target="BTC")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("BTC", 7.5)
        assert len(fired) == 1
        assert "BTC" in fired[0].message

    @pytest.mark.anyio
    async def test_fires_on_negative_change(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=5.0, target="ETH")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("ETH", -8.0)
        assert len(fired) == 1
        assert "down" in fired[0].message

    @pytest.mark.anyio
    async def test_does_not_fire_below_threshold(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=5.0, target="BTC")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("BTC", 2.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_does_not_fire_wrong_symbol(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=5.0, target="BTC")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("ETH", 99.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_no_threshold_does_not_fire(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=None, target="BTC")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("BTC", 99.0)
        assert len(fired) == 0

    @pytest.mark.anyio
    async def test_message_includes_direction_up(self):
        svc = AlertService()
        rule = _make_rule(1, condition="price_change", threshold=1.0, target="BTC")
        await svc.reload_rules([rule])
        fired = await svc.check_price_change("BTC", 3.5)
        assert "up" in fired[0].message


# ---------------------------------------------------------------------------
# AlertService lifecycle: start / stop
# ---------------------------------------------------------------------------


class TestAlertServiceLifecycle:
    """Tests for start() and stop() task management."""

    @pytest.mark.anyio
    async def test_start_creates_background_task(self):
        svc = AlertService()
        await svc.start()
        try:
            assert svc._check_task is not None
            assert not svc._check_task.done()
        finally:
            await svc.stop()

    @pytest.mark.anyio
    async def test_stop_cancels_task(self):
        svc = AlertService()
        await svc.start()
        await svc.stop()
        assert svc._check_task.done()

    @pytest.mark.anyio
    async def test_stop_without_start_does_not_raise(self):
        svc = AlertService()
        await svc.stop()  # must not raise


# ---------------------------------------------------------------------------
# _point_in_bbox edge cases (lines 119-124)
# ---------------------------------------------------------------------------


class TestPointInBboxEdgeCases:
    """Test the _point_in_bbox static method's error branches."""

    def test_wrong_part_count_returns_false(self):
        # Only 3 parts instead of 4
        assert AlertService._point_in_bbox(0.0, 0.0, "0,0,1") is False

    def test_too_many_parts_returns_false(self):
        assert AlertService._point_in_bbox(0.0, 0.0, "0,0,1,1,2") is False

    def test_non_numeric_returns_false(self):
        # Should trigger ValueError in float conversion
        assert AlertService._point_in_bbox(0.0, 0.0, "a,b,c,d") is False

    def test_none_bbox_raises_attribute_error_returns_false(self):
        # Passing None should trigger AttributeError (.split on None)
        assert AlertService._point_in_bbox(0.0, 0.0, None) is False  # type: ignore


# ---------------------------------------------------------------------------
# check_attack_event – disabled rule branch (line 70)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_attack_event_disabled_rule_skipped():
    """A disabled rule should be skipped."""
    svc = AlertService()
    disabled_rule = _make_rule(1, condition="attack_type", target="DDoS", enabled=False)
    await svc.reload_rules([disabled_rule])
    fired = await svc.check_attack_event({"attack_type": "DDoS", "dest_country": "US"})
    assert fired == []


# ---------------------------------------------------------------------------
# check_country_risk – various branch hits (lines 134, 136, 140)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_country_risk_disabled_rule_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="risk_above", threshold=50.0, enabled=False)
    await svc.reload_rules([rule])
    fired = await svc.check_country_risk("RU", 90.0)
    assert fired == []


@pytest.mark.anyio
async def test_check_country_risk_wrong_condition_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="attack_type", threshold=50.0)  # wrong condition
    await svc.reload_rules([rule])
    fired = await svc.check_country_risk("RU", 90.0)
    assert fired == []


@pytest.mark.anyio
async def test_check_country_risk_target_mismatch_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="risk_above", threshold=50.0, target="CN")
    await svc.reload_rules([rule])
    fired = await svc.check_country_risk("RU", 90.0)
    assert fired == []


@pytest.mark.anyio
async def test_check_country_risk_none_threshold_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="risk_above", threshold=None)
    await svc.reload_rules([rule])
    fired = await svc.check_country_risk("RU", 90.0)
    assert fired == []


# ---------------------------------------------------------------------------
# check_attack (line 189 and 191)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_attack_disabled_rule_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="attack_type", target="DDoS", enabled=False)
    await svc.reload_rules([rule])
    fired = await svc.check_attack("DDoS", "US")
    assert fired == []


@pytest.mark.anyio
async def test_check_attack_target_mismatch_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="attack_type", target="SQLi")
    await svc.reload_rules([rule])
    fired = await svc.check_attack("DDoS", "US")
    assert fired == []


# ---------------------------------------------------------------------------
# _background_check loop (lines 245-252)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_background_check_runs_periodic_checks():
    import asyncio
    from unittest.mock import AsyncMock, patch

    svc = AlertService()
    call_count = {"n": 0}

    async def _fake_checks():
        call_count["n"] += 1

    sleep_count = {"n": 0}

    async def _fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            raise asyncio.CancelledError()

    with (
        patch.object(svc, "_run_periodic_checks", _fake_checks),
        patch("asyncio.sleep", _fake_sleep),
    ):
        try:
            await svc._background_check()
        except asyncio.CancelledError:
            pass

    assert call_count["n"] >= 1


@pytest.mark.anyio
async def test_background_check_swallows_exception():
    import asyncio
    from unittest.mock import patch

    svc = AlertService()
    sleep_count = {"n": 0}

    async def _fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            raise asyncio.CancelledError()

    async def _raise_check():
        raise RuntimeError("check failed")

    with (
        patch.object(svc, "_run_periodic_checks", _raise_check),
        patch("asyncio.sleep", _fake_sleep),
    ):
        try:
            await svc._background_check()
        except asyncio.CancelledError:
            pass

    assert sleep_count["n"] >= 1


# ---------------------------------------------------------------------------
# _run_periodic_checks (lines 256-277)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_periodic_checks_calls_services():
    from unittest.mock import AsyncMock, MagicMock, patch
    from types import SimpleNamespace

    svc = AlertService()

    mock_risk_service = AsyncMock()
    mock_risk_service.get_all_scores = AsyncMock(return_value=[])

    mock_anomaly_detector = MagicMock()
    mock_anomaly_detector.get_stats = MagicMock(return_value={"anomaly_score": 0.0})

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()

    with (
        patch("app.services.alert_service.country_risk_service", mock_risk_service, create=True),
        patch("app.services.alert_service.anomaly_detector", mock_anomaly_detector, create=True),
        patch("app.services.alert_service.ws_manager", mock_ws, create=True),
        patch(
            "app.services.alert_service.AlertService._run_periodic_checks",
            wraps=svc._run_periodic_checks,
        ),
    ):
        # Directly call _run_periodic_checks with mocked imports
        from unittest.mock import patch as mp
        with (
            mp("app.services.anomaly_detector.anomaly_detector", mock_anomaly_detector, create=True),
            mp("app.services.country_risk.country_risk_service", mock_risk_service, create=True),
            mp("app.services.websocket_manager.ws_manager", mock_ws, create=True),
        ):
            # Just verify it doesn't crash when called with empty rules
            await svc._run_periodic_checks()


# ---------------------------------------------------------------------------
# check_price_change – disabled rule and wrong condition branches (lines 189, 191)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_price_change_disabled_rule_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="price_change", threshold=3.0, enabled=False)
    await svc.reload_rules([rule])
    fired = await svc.check_price_change("BTC", 10.0)
    assert fired == []


@pytest.mark.anyio
async def test_check_price_change_wrong_condition_skipped():
    svc = AlertService()
    rule = _make_rule(1, condition="risk_above", threshold=3.0)  # wrong condition
    await svc.reload_rules([rule])
    fired = await svc.check_price_change("BTC", 10.0)
    assert fired == []


# ---------------------------------------------------------------------------
# _run_periodic_checks – with actual fired alerts (lines 262-265, 276-277)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_periodic_checks_broadcasts_country_risk_alerts():
    """_run_periodic_checks broadcasts when country_risk alerts fire."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    svc = AlertService()
    # Add a risk_above rule
    rule = _make_rule(1, condition="risk_above", threshold=50.0)
    await svc.reload_rules([rule])

    # Mock score that EXCEEDS threshold
    score = SimpleNamespace(iso2="RU", risk_score=90.0)

    mock_risk_service = AsyncMock()
    mock_risk_service.get_all_scores = AsyncMock(return_value=[score])

    mock_anomaly = MagicMock()
    mock_anomaly.get_stats = MagicMock(return_value={"anomaly_score": 0.0})

    broadcast_calls = []

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock(side_effect=lambda msg: broadcast_calls.append(msg))

    with (
        patch("app.services.alert_service.country_risk_service", mock_risk_service, create=True),
        patch("app.services.alert_service.anomaly_detector", mock_anomaly, create=True),
        patch("app.services.alert_service.ws_manager", mock_ws, create=True),
    ):
        from app.services import alert_service as _as_module
        _as_module.country_risk_service = mock_risk_service
        _as_module.anomaly_detector = mock_anomaly
        _as_module.ws_manager = mock_ws

        with (
            patch("app.services.country_risk.country_risk_service", mock_risk_service, create=True),
            patch("app.services.websocket_manager.ws_manager", mock_ws, create=True),
        ):
            await svc._run_periodic_checks()

    # At least one broadcast for the country risk alert
    assert any(c.get("type") == "alert" for c in broadcast_calls)


@pytest.mark.anyio
async def test_run_periodic_checks_broadcasts_anomaly_alerts():
    """_run_periodic_checks broadcasts when anomaly_score alerts fire."""
    from unittest.mock import AsyncMock, MagicMock, patch

    svc = AlertService()
    # Add anomaly_score rule with low threshold
    rule = _make_rule(1, condition="anomaly_score", threshold=0.3)
    await svc.reload_rules([rule])

    mock_risk_service = AsyncMock()
    mock_risk_service.get_all_scores = AsyncMock(return_value=[])

    mock_anomaly = MagicMock()
    mock_anomaly.get_stats = MagicMock(return_value={"anomaly_score": 0.9})  # exceeds threshold

    broadcast_calls = []
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock(side_effect=lambda msg: broadcast_calls.append(msg))

    with (
        patch("app.services.country_risk.country_risk_service", mock_risk_service, create=True),
        patch("app.services.websocket_manager.ws_manager", mock_ws, create=True),
    ):
        # Patch the imports inside _run_periodic_checks
        import sys
        orig_risk = sys.modules.get("app.services.country_risk")
        orig_ws = sys.modules.get("app.services.websocket_manager")

        mock_cr_module = MagicMock()
        mock_cr_module.country_risk_service = mock_risk_service
        sys.modules["app.services.country_risk"] = mock_cr_module

        mock_ad_module = MagicMock()
        mock_ad_module.anomaly_detector = mock_anomaly
        sys.modules["app.services.anomaly_detector"] = mock_ad_module

        mock_ws_module = MagicMock()
        mock_ws_module.ws_manager = mock_ws
        sys.modules["app.services.websocket_manager"] = mock_ws_module

        try:
            await svc._run_periodic_checks()
        finally:
            if orig_risk:
                sys.modules["app.services.country_risk"] = orig_risk
            if orig_ws:
                sys.modules["app.services.websocket_manager"] = orig_ws
            # Restore anomaly_detector
            if "app.services.anomaly_detector" in sys.modules:
                del sys.modules["app.services.anomaly_detector"]

    assert any(c.get("type") == "alert" for c in broadcast_calls)
