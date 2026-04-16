"""Unit tests for AttackGenerator.

Tests cover: _generate_severity (all branches), generate_event (field
presence, types, severity range), start/stop lifecycle, and idempotent start.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.generator import AttackGenerator

# ---------------------------------------------------------------------------
# _generate_severity – static method, no I/O needed
# ---------------------------------------------------------------------------


class TestGenerateSeverity:
    """Verify the severity distribution for each attack-type category."""

    HIGH_TYPES = ("ZeroDay", "Ransomware", "Intrusion")
    LOW_TYPES = ("XSS", "Phishing", "BruteForce")
    MED_TYPES = ("DDoS", "Malware", "SQLInjection")

    def _check_range(
        self, attack_type: str, lo: int, hi: int, trials: int = 30
    ) -> None:
        for _ in range(trials):
            s = AttackGenerator._generate_severity(attack_type)
            assert lo <= s <= hi, f"{attack_type}: severity {s} outside [{lo}, {hi}]"
            assert isinstance(s, int)

    def test_high_severity_types(self):
        for t in self.HIGH_TYPES:
            self._check_range(t, 6, 10)

    def test_low_severity_types(self):
        for t in self.LOW_TYPES:
            self._check_range(t, 1, 6)

    def test_medium_severity_types(self):
        for t in self.MED_TYPES:
            self._check_range(t, 3, 8)

    def test_unknown_type_returns_medium_range(self):
        self._check_range("Unknown", 3, 8)

    def test_returns_int(self):
        for t in (*self.HIGH_TYPES, *self.LOW_TYPES, *self.MED_TYPES):
            assert isinstance(AttackGenerator._generate_severity(t), int)


# ---------------------------------------------------------------------------
# generate_event – field shape and value constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_event_returns_required_fields():
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    event = await gen.generate_event()
    required = [
        "id",
        "source_ip",
        "dest_ip",
        "source_country",
        "dest_country",
        "source_lat",
        "source_lng",
        "dest_lat",
        "dest_lng",
        "attack_type",
        "severity",
        "timestamp",
        "cluster_id",
    ]
    for field in required:
        assert field in event, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_generate_event_severity_in_range():
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    for _ in range(10):
        event = await gen.generate_event()
        assert 1 <= event["severity"] <= 10


@pytest.mark.asyncio
async def test_generate_event_cluster_id_is_none():
    """cluster_id is set later by the processor — generator always emits None."""
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    event = await gen.generate_event()
    assert event["cluster_id"] is None


@pytest.mark.asyncio
async def test_generate_event_attack_type_valid():
    valid_types = {
        "DDoS",
        "BruteForce",
        "Malware",
        "Phishing",
        "SQLInjection",
        "Intrusion",
        "XSS",
        "Ransomware",
        "ZeroDay",
    }
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    for _ in range(20):
        event = await gen.generate_event()
        assert event["attack_type"] in valid_types


@pytest.mark.asyncio
async def test_generate_event_ip_not_empty():
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    event = await gen.generate_event()
    assert event["source_ip"] != ""
    assert event["dest_ip"] != ""


@pytest.mark.asyncio
async def test_generate_event_id_is_uuid_string():
    import re

    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    queue: asyncio.Queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    event = await gen.generate_event()
    assert uuid_re.match(event["id"]), f"id {event['id']!r} is not a UUID"


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_sets_running_true():
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    gen = AttackGenerator(queue)
    await gen.start()
    try:
        assert gen._running is True
        assert gen._task is not None
    finally:
        await gen.stop()


@pytest.mark.asyncio
async def test_stop_sets_running_false():
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    gen = AttackGenerator(queue)
    await gen.start()
    await gen.stop()
    assert gen._running is False


@pytest.mark.asyncio
async def test_start_idempotent():
    """Calling start() twice must not create a second task."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    gen = AttackGenerator(queue)
    await gen.start()
    first_task = gen._task
    await gen.start()  # second call — should be no-op
    assert gen._task is first_task
    await gen.stop()


@pytest.mark.asyncio
async def test_generator_puts_events_on_queue():
    """Let the generator run briefly and confirm at least one event lands."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    gen = AttackGenerator(queue)
    await gen.start()
    await asyncio.sleep(0.15)  # at 1 eps default, should get at least 1 event
    await gen.stop()
    assert queue.qsize() >= 1


# ---------------------------------------------------------------------------
# Generator loop edge cases (lines 101, 167-168, 172-174)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_loop_queue_full_drops_event():
    """When the queue is full, QueueFull is caught and event is dropped."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.generator import AttackGenerator

    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait({"id": "filler"})  # Fill queue to maxsize

    gen = AttackGenerator(queue)
    gen._running = True

    call_count = {"n": 0}

    async def fake_generate_event():
        call_count["n"] += 1
        return {"id": "new_event", "type": "test"}

    sleep_count = {"n": 0}

    async def fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 1:
            gen._running = False
            raise asyncio.CancelledError()

    with (
        patch.object(gen, "generate_event", fake_generate_event),
        patch("asyncio.sleep", fake_sleep),
    ):
        try:
            await gen._loop()
        except asyncio.CancelledError:
            pass

    # QueueFull should have been swallowed, and generate was called
    assert call_count["n"] >= 1


@pytest.mark.anyio
async def test_loop_swallows_exception():
    """Generic exception in generate_event is swallowed and loop continues."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.services.generator import AttackGenerator

    queue = asyncio.Queue()
    gen = AttackGenerator(queue)
    gen._running = True

    call_count = {"n": 0}

    async def fake_generate_raises():
        call_count["n"] += 1
        raise RuntimeError("generate failed")

    sleep_count = {"n": 0}

    async def fake_sleep(_):
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            gen._running = False
            raise asyncio.CancelledError()

    with (
        patch.object(gen, "generate_event", fake_generate_raises),
        patch("asyncio.sleep", fake_sleep),
    ):
        try:
            await gen._loop()
        except asyncio.CancelledError:
            pass

    assert call_count["n"] >= 1
    assert sleep_count["n"] >= 2


# ---------------------------------------------------------------------------
# generate_event – empty dst_weights fallback (line 101)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_generate_event_dst_weights_fallback():
    """When all target countries are filtered out, dst_weights falls back to uniform."""
    import asyncio
    from unittest.mock import patch

    from app.services import generator as gen_module
    from app.services.generator import AttackGenerator

    queue = asyncio.Queue()
    gen = AttackGenerator(queue)

    # Force src_code to match ALL target countries, making dst_weights empty.
    # We do this by making _TARGET_COUNTRIES_WEIGHTED contain only the same code
    # as _SRC_CODES with uniform weights.
    with (
        patch.object(gen_module, "_SRC_CODES", ("US",)),
        patch.object(gen_module, "_SRC_WEIGHTS", (1,)),
        patch.object(gen_module, "_DST_CODES", ("US",)),
        patch.object(gen_module, "_TARGET_COUNTRIES_WEIGHTED", [("US", 10)]),
    ):
        event = await gen.generate_event()

    # The fallback should produce an event (dst_code will be "US" since it's the
    # only candidate)
    assert "source_ip" in event
