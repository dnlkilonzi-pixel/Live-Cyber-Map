"""Unit tests for AnomalyDetector.

Tests cover: add_event, get_stats, get_top_attackers, get_top_targets,
get_attack_type_stats, sliding-window eviction, and per-second bucketing.
"""

from __future__ import annotations

import time

from app.services.anomaly_detector import _WINDOW_SECONDS, AnomalyDetector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(
    src_ip: str = "1.1.1.1",
    src_country: str = "CN",
    dest_country: str = "US",
    attack_type: str = "DDoS",
) -> dict:
    return {
        "source_ip": src_ip,
        "source_country": src_country,
        "dest_country": dest_country,
        "attack_type": attack_type,
    }


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_stats_are_zero():
    d = AnomalyDetector()
    stats = d.get_stats()
    assert stats["events_per_second"] == 0.0
    assert stats["current_rate"] == 0
    assert stats["total_events_in_window"] == 0
    assert stats["is_anomaly"] is False
    assert stats["anomaly_score"] == 0.0


def test_initial_top_attackers_empty():
    d = AnomalyDetector()
    assert d.get_top_attackers() == []


def test_initial_top_targets_empty():
    d = AnomalyDetector()
    assert d.get_top_targets() == []


def test_initial_attack_type_stats_empty():
    d = AnomalyDetector()
    assert d.get_attack_type_stats() == {}


# ---------------------------------------------------------------------------
# add_event – window accounting
# ---------------------------------------------------------------------------

def test_add_event_appears_in_window():
    d = AnomalyDetector()
    d.add_event(_event())
    assert d.get_stats()["total_events_in_window"] == 1


def test_add_multiple_events_counted():
    d = AnomalyDetector()
    for _ in range(7):
        d.add_event(_event())
    assert d.get_stats()["total_events_in_window"] == 7


def test_events_outside_window_are_evicted():
    d = AnomalyDetector()
    old_ts = time.time() - _WINDOW_SECONDS - 5
    d._window.append((old_ts, _event()))
    d.add_event(_event())  # fresh event triggers eviction
    assert d.get_stats()["total_events_in_window"] == 1


# ---------------------------------------------------------------------------
# add_event – counters
# ---------------------------------------------------------------------------

def test_attacker_counter_increments():
    d = AnomalyDetector()
    d.add_event(_event(src_ip="5.5.5.5"))
    d.add_event(_event(src_ip="5.5.5.5"))
    attackers = d.get_top_attackers(1)
    assert attackers[0]["ip"] == "5.5.5.5"
    assert attackers[0]["count"] == 2


def test_top_attackers_sorted_by_count():
    d = AnomalyDetector()
    for _ in range(3):
        d.add_event(_event(src_ip="1.1.1.1"))
    d.add_event(_event(src_ip="2.2.2.2"))
    attackers = d.get_top_attackers(2)
    assert attackers[0]["ip"] == "1.1.1.1"
    assert attackers[1]["ip"] == "2.2.2.2"


def test_attacker_country_cached_on_first_seen():
    d = AnomalyDetector()
    d.add_event(_event(src_ip="7.7.7.7", src_country="RU"))
    # Same IP, different country label — should NOT override first entry
    d.add_event(_event(src_ip="7.7.7.7", src_country="CN"))
    attackers = d.get_top_attackers(1)
    assert attackers[0]["country"] == "RU"


def test_target_counter_increments():
    d = AnomalyDetector()
    d.add_event(_event(dest_country="DE"))
    d.add_event(_event(dest_country="DE"))
    d.add_event(_event(dest_country="US"))
    targets = d.get_top_targets(2)
    assert targets[0]["country"] == "DE"
    assert targets[0]["count"] == 2


def test_attack_type_stats():
    d = AnomalyDetector()
    d.add_event(_event(attack_type="DDoS"))
    d.add_event(_event(attack_type="DDoS"))
    d.add_event(_event(attack_type="Malware"))
    stats = d.get_attack_type_stats()
    assert stats["DDoS"] == 2
    assert stats["Malware"] == 1


# ---------------------------------------------------------------------------
# add_event – per-second bucketing
# ---------------------------------------------------------------------------

def test_per_second_bucket_flush_on_new_second():
    d = AnomalyDetector()
    d.add_event(_event())
    # Simulate 1 second passing by rolling back _current_second
    d._current_second -= 1
    d.add_event(_event())
    # At least one completed bucket should now be present
    assert len(d._second_buckets) >= 1


def test_gap_seconds_filled_with_zeros():
    d = AnomalyDetector()
    d.add_event(_event())
    # Simulate a 3-second gap
    d._current_second -= 3
    d.add_event(_event())
    # At least 3 zero-buckets should have been appended
    assert len(d._second_buckets) >= 1


# ---------------------------------------------------------------------------
# get_stats – derived fields
# ---------------------------------------------------------------------------

def test_events_per_second_nonzero():
    d = AnomalyDetector()
    for _ in range(10):
        d.add_event(_event())
    stats = d.get_stats()
    assert stats["events_per_second"] > 0.0


def test_anomaly_score_non_negative():
    d = AnomalyDetector()
    for _ in range(5):
        d.add_event(_event())
    stats = d.get_stats()
    assert stats["anomaly_score"] >= 0.0


def test_stats_keys_present():
    d = AnomalyDetector()
    stats = d.get_stats()
    expected_keys = {
        "events_per_second",
        "current_rate",
        "rolling_avg",
        "window_size_seconds",
        "total_events_in_window",
        "is_anomaly",
        "anomaly_score",
    }
    assert expected_keys.issubset(stats.keys())


# ---------------------------------------------------------------------------
# get_top_attackers / get_top_targets — limit respected
# ---------------------------------------------------------------------------

def test_top_attackers_limit():
    d = AnomalyDetector()
    for i in range(10):
        d.add_event(_event(src_ip=f"10.0.0.{i}"))
    assert len(d.get_top_attackers(3)) == 3


def test_top_targets_limit():
    d = AnomalyDetector()
    countries = ["US", "DE", "FR", "GB", "JP"]
    for c in countries:
        d.add_event(_event(dest_country=c))
    assert len(d.get_top_targets(2)) == 2
