"""Unit tests for CountryRiskService.

Tests cover: start/stop, get_all_scores, get_country_score, record_attack,
update_news_sentiment, _recompute_scores, and _country_to_iso2.
"""

from __future__ import annotations

import pytest

from app.services.country_risk import _BASELINE, CountryRiskService

# ---------------------------------------------------------------------------
# Fixture: fresh service instance per test
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> CountryRiskService:
    return CountryRiskService()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_init_creates_scores_for_all_baseline_countries(svc):
    assert len(svc._scores) == len(_BASELINE)


def test_init_scores_have_nonzero_risk(svc):
    for iso2, country in svc._scores.items():
        assert country.risk_score >= 0, f"{iso2}: negative risk score"


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_creates_background_task(svc):
    await svc.start()
    try:
        assert svc._update_task is not None
        assert not svc._update_task.done()
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task(svc):
    await svc.start()
    await svc.stop()
    assert svc._update_task.done()


@pytest.mark.asyncio
async def test_stop_without_start_does_not_raise(svc):
    await svc.stop()  # must not raise


# ---------------------------------------------------------------------------
# get_all_scores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_scores_returns_list(svc):
    scores = await svc.get_all_scores()
    assert isinstance(scores, list)
    assert len(scores) == len(_BASELINE)


@pytest.mark.asyncio
async def test_get_all_scores_sorted_descending(svc):
    scores = await svc.get_all_scores()
    for i in range(len(scores) - 1):
        assert scores[i].risk_score >= scores[i + 1].risk_score


# ---------------------------------------------------------------------------
# get_country_score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_country_score_known_country(svc):
    score = await svc.get_country_score("US")
    assert score is not None
    assert score.iso2 == "US"


@pytest.mark.asyncio
async def test_get_country_score_case_insensitive(svc):
    score = await svc.get_country_score("us")
    assert score is not None
    assert score.iso2 == "US"


@pytest.mark.asyncio
async def test_get_country_score_unknown_returns_none(svc):
    score = await svc.get_country_score("ZZ")
    assert score is None


# ---------------------------------------------------------------------------
# record_attack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_attack_increments_count(svc):
    await svc.record_attack("United States")
    assert svc._attack_counts.get("US", 0) == 1


@pytest.mark.asyncio
async def test_record_attack_multiple_times(svc):
    for _ in range(5):
        await svc.record_attack("Russia")
    assert svc._attack_counts.get("RU", 0) == 5


@pytest.mark.asyncio
async def test_record_attack_unknown_country_does_not_raise(svc):
    await svc.record_attack("UnknownLand")  # must not raise


@pytest.mark.asyncio
async def test_record_attack_by_iso2_code(svc):
    await svc.record_attack("DE")
    assert svc._attack_counts.get("DE", 0) == 1


# ---------------------------------------------------------------------------
# update_news_sentiment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_news_sentiment_sets_value(svc):
    await svc.update_news_sentiment("United States", -0.5)
    assert "US" in svc._news_sentiments


@pytest.mark.asyncio
async def test_update_news_sentiment_ema(svc):
    """Repeated updates converge via EMA."""
    for _ in range(10):
        await svc.update_news_sentiment("Germany", -1.0)
    # After many -1.0 sentiment updates, value should be negative
    assert svc._news_sentiments["DE"] < 0


@pytest.mark.asyncio
async def test_update_news_sentiment_unknown_country(svc):
    await svc.update_news_sentiment("UnknownLand", 0.5)  # must not raise


# ---------------------------------------------------------------------------
# _recompute_scores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recompute_scores_updates_cyber_score(svc):
    svc._attack_counts["US"] = 50
    await svc._recompute_scores()
    score = svc._scores.get("US")
    assert score is not None
    assert score.cyber_score > 0.0


@pytest.mark.asyncio
async def test_recompute_scores_decays_attack_counts(svc):
    svc._attack_counts["US"] = 10
    await svc._recompute_scores()
    # Count should decay by 1 after recompute
    assert svc._attack_counts.get("US", 0) == 9


@pytest.mark.asyncio
async def test_recompute_scores_no_attacks_zero_cyber(svc):
    await svc._recompute_scores()
    # With no attacks, cyber_score should remain 0 for all countries
    for score in svc._scores.values():
        assert score.cyber_score == 0.0


@pytest.mark.asyncio
async def test_recompute_scores_risk_capped_at_100(svc):
    # Flood attack counts to max out cyber score
    for iso2 in svc._scores:
        svc._attack_counts[iso2] = 10000
    await svc._recompute_scores()
    for score in svc._scores.values():
        assert score.risk_score <= 100.0


# ---------------------------------------------------------------------------
# _country_to_iso2
# ---------------------------------------------------------------------------


def test_country_to_iso2_exact_name(svc):
    assert svc._country_to_iso2("United States") == "US"


def test_country_to_iso2_alias(svc):
    assert svc._country_to_iso2("usa") == "US"
    assert svc._country_to_iso2("russia") == "RU"
    assert svc._country_to_iso2("china") == "CN"


def test_country_to_iso2_two_letter_code(svc):
    assert svc._country_to_iso2("DE") == "DE"
    assert svc._country_to_iso2("jp") == "JP"


def test_country_to_iso2_unknown_returns_none(svc):
    assert svc._country_to_iso2("UnknownLand") is None


def test_country_to_iso2_case_insensitive(svc):
    assert svc._country_to_iso2("GERMANY") == "DE"


# ---------------------------------------------------------------------------
# _background_update loop (lines 295-302)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_background_update_runs_recompute():
    """_background_update calls _recompute_scores and loops."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.services.country_risk import CountryRiskService

    svc = CountryRiskService()
    call_count = {"n": 0}

    async def fake_recompute():
        call_count["n"] += 1

    sleep_count = {"n": 0}

    async def fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            raise asyncio.CancelledError()

    with (
        patch.object(svc, "_recompute_scores", fake_recompute),
        patch("asyncio.sleep", fake_sleep),
    ):
        try:
            await svc._background_update()
        except asyncio.CancelledError:
            pass

    assert call_count["n"] >= 1


@pytest.mark.anyio
async def test_background_update_swallows_exception():
    """Non-CancelledError exceptions in _background_update are swallowed."""
    import asyncio
    from unittest.mock import patch

    from app.services.country_risk import CountryRiskService

    svc = CountryRiskService()

    sleep_count = {"n": 0}

    async def fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 3:
            raise asyncio.CancelledError()

    async def raise_recompute():
        raise RuntimeError("recompute failed")

    with (
        patch.object(svc, "_recompute_scores", raise_recompute),
        patch("asyncio.sleep", fake_sleep),
    ):
        try:
            await svc._background_update()
        except asyncio.CancelledError:
            pass

    assert sleep_count["n"] >= 2


# ---------------------------------------------------------------------------
# _persist_snapshots exception handling (line 401)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_persist_snapshots_swallows_error():
    """_persist_snapshots should swallow DB errors silently."""
    from unittest.mock import patch

    from app.services.country_risk import CountryRiskService

    with patch(
        "app.core.database.AsyncSessionLocal",
        side_effect=RuntimeError("DB gone"),
    ):
        await CountryRiskService._persist_snapshots([])  # should not raise
