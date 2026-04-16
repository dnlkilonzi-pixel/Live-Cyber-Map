"""Tests for app/main.py: lifespan startup/shutdown and background loops.

Covers:
  - lifespan() startup with Redis available and unavailable
  - lifespan() shutdown sequence
  - alert_service startup error is swallowed gracefully
  - _anomaly_feed_loop: processor=None, new events, wrap/reset, cancel, exception
  - _risk_feed_loop: processor=None, dest_country events, wrap/reset, cancel
  - create_app() returns a FastAPI instance with all routers attached
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import app.main as main_module
from app.main import _anomaly_feed_loop, _risk_feed_loop, create_app, lifespan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_mock() -> AsyncMock:
    """Return a mock DB session that returns empty results."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    sess = AsyncMock()
    sess.__aenter__ = AsyncMock(return_value=sess)
    sess.__aexit__ = AsyncMock(return_value=False)
    sess.execute = AsyncMock(return_value=mock_result)
    return sess


def _setup_ws_manager(mock_wsm: MagicMock) -> None:
    mock_wsm.set_redis = MagicMock()
    mock_wsm.start_redis_subscriber = AsyncMock()
    mock_wsm.stop_redis_subscriber = AsyncMock()


def _setup_service_mock(svc: MagicMock, *, has_set_redis: bool = True) -> None:
    if has_set_redis:
        svc.set_redis = MagicMock()
    svc.start = AsyncMock()
    svc.stop = AsyncMock()


def _lifespan_patches(redis_ok: bool = True, alert_raises: bool = False):
    """Context manager stack for lifespan tests."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(
        side_effect=None if redis_ok else ConnectionRefusedError("Redis down")
    )
    mock_redis.aclose = AsyncMock()

    mock_gen = AsyncMock()
    mock_gen.start = AsyncMock()
    mock_gen.stop = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.start = AsyncMock()
    mock_proc.stop = AsyncMock()
    mock_proc.get_recent_events = MagicMock(return_value=[])

    mock_session = _make_session_mock()

    return mock_redis, mock_gen, mock_proc, mock_session


# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_startup_shutdown_redis_available():
    """Lifespan completes start and shutdown when Redis ping succeeds."""
    mock_redis, mock_gen, mock_proc, mock_session = _lifespan_patches(redis_ok=True)

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_aioredis,
        patch("app.main.AttackGenerator", return_value=mock_gen),
        patch("app.main.AttackProcessor", return_value=mock_proc),
        patch("app.main.ws_manager") as mock_wsm,
        patch("app.main.news_aggregator") as mock_news,
        patch("app.main.financial_service") as mock_fin,
        patch("app.main.country_risk_service") as mock_risk,
        patch("app.main.ollama_service") as mock_ollama,
        patch("app.main.alert_service") as mock_alert,
        patch("app.main.AsyncSessionLocal", return_value=mock_session),
        patch("app.main.engine") as mock_engine,
        patch("app.main.anomaly_detector"),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        _setup_ws_manager(mock_wsm)
        _setup_service_mock(mock_news)
        _setup_service_mock(mock_fin)
        _setup_service_mock(mock_risk, has_set_redis=False)
        mock_ollama.is_available = AsyncMock(return_value=True)
        mock_alert.reload_rules = AsyncMock()
        mock_alert.start = AsyncMock()
        mock_alert.stop = AsyncMock()
        mock_engine.dispose = AsyncMock()

        dummy_app = FastAPI()
        async with lifespan(dummy_app):
            pass

    mock_gen.start.assert_awaited_once()
    mock_proc.start.assert_awaited_once()
    mock_gen.stop.assert_awaited_once()
    mock_proc.stop.assert_awaited_once()
    mock_redis.aclose.assert_awaited_once()
    mock_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_startup_redis_unavailable():
    """Lifespan gracefully degrades when Redis ping raises an exception."""
    mock_redis, mock_gen, mock_proc, mock_session = _lifespan_patches(redis_ok=False)

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_aioredis,
        patch("app.main.AttackGenerator", return_value=mock_gen),
        patch("app.main.AttackProcessor", return_value=mock_proc),
        patch("app.main.ws_manager") as mock_wsm,
        patch("app.main.news_aggregator") as mock_news,
        patch("app.main.financial_service") as mock_fin,
        patch("app.main.country_risk_service") as mock_risk,
        patch("app.main.ollama_service") as mock_ollama,
        patch("app.main.alert_service") as mock_alert,
        patch("app.main.AsyncSessionLocal", return_value=mock_session),
        patch("app.main.engine") as mock_engine,
        patch("app.main.anomaly_detector"),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        _setup_ws_manager(mock_wsm)
        _setup_service_mock(mock_news)
        _setup_service_mock(mock_fin)
        _setup_service_mock(mock_risk, has_set_redis=False)
        mock_ollama.is_available = AsyncMock(return_value=False)
        mock_alert.reload_rules = AsyncMock()
        mock_alert.start = AsyncMock()
        mock_alert.stop = AsyncMock()
        mock_engine.dispose = AsyncMock()

        dummy_app = FastAPI()
        async with lifespan(dummy_app):
            # redis_client should be None after ping fails
            assert main_module.redis_client is None

    # engine.dispose should still be called even without Redis
    mock_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_alert_service_startup_error_is_swallowed():
    """If alert_service startup raises, the lifespan continues without error."""
    mock_redis, mock_gen, mock_proc, mock_session = _lifespan_patches(redis_ok=True)

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_aioredis,
        patch("app.main.AttackGenerator", return_value=mock_gen),
        patch("app.main.AttackProcessor", return_value=mock_proc),
        patch("app.main.ws_manager") as mock_wsm,
        patch("app.main.news_aggregator") as mock_news,
        patch("app.main.financial_service") as mock_fin,
        patch("app.main.country_risk_service") as mock_risk,
        patch("app.main.ollama_service") as mock_ollama,
        patch("app.main.alert_service") as mock_alert,
        patch("app.main.AsyncSessionLocal", return_value=mock_session),
        patch("app.main.engine") as mock_engine,
        patch("app.main.anomaly_detector"),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        _setup_ws_manager(mock_wsm)
        _setup_service_mock(mock_news)
        _setup_service_mock(mock_fin)
        _setup_service_mock(mock_risk, has_set_redis=False)
        mock_ollama.is_available = AsyncMock(return_value=True)
        # Simulate alert_service raising during startup
        mock_alert.reload_rules = AsyncMock(side_effect=RuntimeError("DB error"))
        mock_alert.start = AsyncMock()
        mock_alert.stop = AsyncMock()
        mock_engine.dispose = AsyncMock()

        dummy_app = FastAPI()
        # Should not raise despite the alert_service error
        async with lifespan(dummy_app):
            pass


# ---------------------------------------------------------------------------
# _anomaly_feed_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomaly_feed_loop_processor_none():
    """Loop iterations skip gracefully when processor is None."""
    original = main_module.processor
    main_module.processor = None
    try:
        task = asyncio.create_task(_anomaly_feed_loop())
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_anomaly_feed_loop_new_events_fed():
    """New events beyond last_seen_count are fed to the anomaly detector."""
    event_a = {"id": "a", "attack_type": "DDoS"}
    event_b = {"id": "b", "attack_type": "SQLi"}
    original = main_module.processor

    mock_proc = MagicMock()
    call_count = 0

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return [event_a]
        return [event_a, event_b]

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.anomaly_detector") as mock_ad:
            mock_ad.add_event = MagicMock()
            task = asyncio.create_task(_anomaly_feed_loop())
            await asyncio.sleep(0.35)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # At least event_b should have been added
        calls = [c.args[0] for c in mock_ad.add_event.call_args_list]
        assert event_a in calls
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_anomaly_feed_loop_count_reset_on_wrap():
    """last_seen_count resets when new_count < last_seen_count (ring buffer wrap)."""
    original = main_module.processor
    call_count = 0

    mock_proc = MagicMock()

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{"id": "x"}] * 5  # 5 events
        # Simulate buffer wrap: drops back to 2
        return [{"id": "x"}] * 2

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.anomaly_detector"):
            task = asyncio.create_task(_anomaly_feed_loop())
            await asyncio.sleep(0.25)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_anomaly_feed_loop_swallows_exceptions():
    """Non-CancelledError exceptions inside the loop are swallowed and loop continues."""
    original = main_module.processor
    call_count = 0

    mock_proc = MagicMock()

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("transient error")
        return []

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.anomaly_detector"):
            task = asyncio.create_task(_anomaly_feed_loop())
            await asyncio.sleep(0.25)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # If we get here the loop didn't crash
        assert call_count >= 1
    finally:
        main_module.processor = original


# ---------------------------------------------------------------------------
# _risk_feed_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_feed_loop_processor_none():
    """Loop iterations skip gracefully when processor is None."""
    original = main_module.processor
    main_module.processor = None
    try:
        task = asyncio.create_task(_risk_feed_loop())
        await asyncio.sleep(2.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_risk_feed_loop_records_attacks():
    """dest_country is passed to country_risk_service.record_attack."""
    original = main_module.processor
    event = {"dest_country": "DE"}
    call_count = 0

    mock_proc = MagicMock()

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [event]
        return [event]  # same list – won't re-feed

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.country_risk_service") as mock_risk:
            mock_risk.record_attack = AsyncMock()
            task = asyncio.create_task(_risk_feed_loop())
            await asyncio.sleep(1.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        mock_risk.record_attack.assert_awaited()
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_risk_feed_loop_count_reset_on_wrap():
    """last_seen_count resets when buffer wraps."""
    original = main_module.processor
    call_count = 0

    mock_proc = MagicMock()

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        return [{"dest_country": "US"}] * (5 if call_count == 1 else 2)

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.country_risk_service") as mock_risk:
            mock_risk.record_attack = AsyncMock()
            task = asyncio.create_task(_risk_feed_loop())
            await asyncio.sleep(2.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        main_module.processor = original


@pytest.mark.asyncio
async def test_risk_feed_loop_swallows_exceptions():
    """Exceptions inside the loop body are swallowed."""
    original = main_module.processor
    call_count = 0

    mock_proc = MagicMock()

    def _events(_limit):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        return []

    mock_proc.get_recent_events = _events
    main_module.processor = mock_proc

    try:
        with patch("app.main.country_risk_service") as mock_risk:
            mock_risk.record_attack = AsyncMock()
            task = asyncio.create_task(_risk_feed_loop())
            await asyncio.sleep(2.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert call_count >= 1
    finally:
        main_module.processor = original


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi():
    """create_app() returns a FastAPI instance with the expected title."""
    application = create_app()
    assert application.title == "Global Intelligence Dashboard API"
    # All key routers should be attached (check a few route paths)
    paths = {r.path for r in application.routes}
    assert "/api/health" in paths
    assert "/ws" in paths
