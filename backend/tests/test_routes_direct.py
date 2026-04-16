"""Direct function-call unit tests for app/api/routes.py.

These bypass the HTTP/ASGI layer and call route functions directly with
mock DB sessions, allowing coverage.py to properly trace async lines
after `await` statements (a known Python 3.12 sys.monitoring limitation).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# health_check – DB ok, DB fail, Redis paths (lines 42, 53-54)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_db_ok():
    from app.api.routes import health_check

    mock_result = MagicMock()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.main.redis_client", None):
        result = await health_check(db=mock_db)

    assert result["database"] == "connected"
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_db_fail():
    from app.api.routes import health_check

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    with patch("app.main.redis_client", None):
        result = await health_check(db=mock_db)

    assert result["database"] == "unavailable"
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_redis_connected():
    from app.api.routes import health_check

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()

    with patch("app.main.redis_client", mock_redis):
        result = await health_check(db=mock_db)

    assert result["redis"] == "connected"


@pytest.mark.asyncio
async def test_health_check_redis_unavailable():
    from app.api.routes import health_check

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionRefusedError("no redis"))

    with patch("app.main.redis_client", mock_redis):
        result = await health_check(db=mock_db)

    assert result["redis"] == "unavailable"


# ---------------------------------------------------------------------------
# get_attack_history – filter branches (lines 138-139)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_attack_history_direct_no_rows():
    from app.api.routes import get_attack_history

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await get_attack_history(
        attack_type=None,
        source_country=None,
        dest_country=None,
        min_severity=None,
        max_severity=None,
        limit=50,
        offset=0,
        db=mock_db,
    )
    assert result == []


@pytest.mark.asyncio
async def test_get_attack_history_with_all_filters():
    from app.api.routes import get_attack_history

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await get_attack_history(
        attack_type="DDoS",
        source_country="RU",
        dest_country="US",
        min_severity=3,
        max_severity=9,
        limit=20,
        offset=10,
        db=mock_db,
    )
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_attack_history_db_error_raises_503():
    from fastapi import HTTPException

    from app.api.routes import get_attack_history

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB gone"))

    with pytest.raises(HTTPException) as exc_info:
        await get_attack_history(
            attack_type=None,
            source_country=None,
            dest_country=None,
            min_severity=None,
            max_severity=None,
            limit=50,
            offset=0,
            db=mock_db,
        )
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# seek_replay – direct call with mock DB (lines 201-224)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seek_replay_direct_no_rows():
    from app.api.routes import seek_replay

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.api.routes.ws_manager.broadcast", new_callable=AsyncMock
    ) as mock_broadcast:
        result = await seek_replay(position=0, db=mock_db)

    assert result["status"] == "seek"
    assert result["position"] == 0
    mock_broadcast.assert_called()


@pytest.mark.asyncio
async def test_seek_replay_direct_with_rows():
    from app.api.routes import seek_replay

    # Build a fake AttackEvent row
    row = MagicMock()
    row.id = 1
    row.source_ip = "1.2.3.4"
    row.source_country = "RU"
    row.source_lat = 55.75
    row.source_lng = 37.62
    row.dest_ip = "5.6.7.8"
    row.dest_country = "US"
    row.dest_lat = 37.77
    row.dest_lng = -122.42
    row.attack_type = "DDoS"
    row.severity = 7
    row.cluster_id = None
    row.timestamp = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    broadcast_calls = []

    async def capture(msg):
        broadcast_calls.append(msg)

    with patch("app.api.routes.ws_manager.broadcast", side_effect=capture):
        result = await seek_replay(position=5, db=mock_db)

    assert result["position"] == 5
    # Should have broadcast the replay_seek + the attack event
    assert any(c.get("type") == "replay_seek" for c in broadcast_calls)
    assert any(c.get("type") == "attack" for c in broadcast_calls)


@pytest.mark.asyncio
async def test_seek_replay_db_error_swallowed():
    """DB error in seek_replay is swallowed, still returns status=seek."""
    from app.api.routes import seek_replay

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB gone"))

    with patch("app.api.routes.ws_manager.broadcast", new_callable=AsyncMock):
        result = await seek_replay(position=0, db=mock_db)

    assert result["status"] == "seek"


# ---------------------------------------------------------------------------
# get_replay_intelligence – direct call with mock DB (lines 284-326)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_replay_intelligence_direct_empty():
    from app.api.routes import get_replay_intelligence

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await get_replay_intelligence(
        from_ts=None, to_ts=None, limit=500, db=mock_db
    )

    assert "events" in result
    assert "total" in result
    assert "from" in result
    assert "to" in result
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_replay_intelligence_direct_with_time_range():
    from app.api.routes import get_replay_intelligence

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await get_replay_intelligence(
        from_ts=1700000000.0, to_ts=1700086400.0, limit=100, db=mock_db
    )

    assert result["total"] == 0
    assert "from" in result


@pytest.mark.asyncio
async def test_get_replay_intelligence_with_risk_and_financial_rows():
    """Simulate actual risk + financial rows to cover list comprehensions."""
    from app.api.routes import get_replay_intelligence

    # Build a fake risk row
    risk_row = MagicMock()
    risk_row.snapshotted_at = datetime.now(timezone.utc)
    risk_row.iso2 = "RU"
    risk_row.risk_score = 75.3
    risk_row.cyber_score = 80.1
    risk_row.news_score = 70.5
    risk_row.attack_count_24h = 12

    # Build a fake financial row
    fin_row = MagicMock()
    fin_row.snapshotted_at = datetime.now(timezone.utc)
    fin_row.symbol = "BTC"
    fin_row.asset_class = "crypto"
    fin_row.price = 42000.0
    fin_row.change_pct = 2.5

    call_count = {"n": 0}

    async def smart_execute(stmt):
        call_count["n"] += 1
        mock_result = MagicMock()
        if call_count["n"] == 1:
            mock_result.scalars.return_value.all.return_value = [risk_row]
        else:
            mock_result.scalars.return_value.all.return_value = [fin_row]
        return mock_result

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=smart_execute)

    result = await get_replay_intelligence(
        from_ts=None, to_ts=None, limit=500, db=mock_db
    )

    assert result["total"] == 2
    types = [e["type"] for e in result["events"]]
    assert "risk" in types
    assert "financial" in types


@pytest.mark.asyncio
async def test_get_replay_intelligence_db_error_returns_503():
    from fastapi import HTTPException

    from app.api.routes import get_replay_intelligence

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB gone"))

    with pytest.raises(HTTPException) as exc_info:
        await get_replay_intelligence(
            from_ts=None, to_ts=None, limit=500, db=mock_db
        )
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# get_stats – direct call (line 73)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_direct():
    from app.api.routes import get_stats

    result = await get_stats()
    assert "rates" in result
    assert "top_attackers" in result
    assert "attack_types" in result
    assert "ws_connections" in result


# ---------------------------------------------------------------------------
# get_recent_attacks – no processor and with processor (lines 92-98)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_attacks_direct_no_processor():
    from app.api.routes import get_recent_attacks

    with patch("app.main.processor", None):
        result = await get_recent_attacks(limit=100)

    assert result["count"] == 0
    assert result["events"] == []


@pytest.mark.asyncio
async def test_get_recent_attacks_direct_with_processor():
    from app.api.routes import get_recent_attacks

    mock_proc = MagicMock()
    mock_proc.get_recent_events = MagicMock(return_value=[{"id": "1"}])

    with patch("app.main.processor", mock_proc):
        result = await get_recent_attacks(limit=50)

    assert result["count"] == 1


# ---------------------------------------------------------------------------
# get_replay_status, start_replay, stop_replay (lines 153, 159-162, 168-171)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_replay_status_direct():
    from app.api.routes import get_replay_status, _replay_state

    result = await get_replay_status()
    assert result is _replay_state


@pytest.mark.asyncio
async def test_start_replay_direct():
    from app.api.routes import start_replay

    with patch(
        "app.api.routes.ws_manager.broadcast", new_callable=AsyncMock
    ) as mock_broadcast:
        result = await start_replay(speed=2.5)

    assert result["speed"] == 2.5
    assert "replay started" in result["status"]
    mock_broadcast.assert_called_once()
    args = mock_broadcast.call_args[0][0]
    assert args["type"] == "replay_started"


@pytest.mark.asyncio
async def test_stop_replay_direct():
    from app.api.routes import stop_replay

    with patch(
        "app.api.routes.ws_manager.broadcast", new_callable=AsyncMock
    ) as mock_broadcast:
        result = await stop_replay()

    assert "replay stopped" in result["status"]
    mock_broadcast.assert_called_once()
    args = mock_broadcast.call_args[0][0]
    assert args["type"] == "replay_stopped"
