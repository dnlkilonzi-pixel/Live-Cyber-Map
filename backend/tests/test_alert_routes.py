"""Tests for app/api/alert_routes.py – full CRUD coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_client():
    engine = create_async_engine(_SQLITE_URL, echo=False)
    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        from app.models import alert, attack, financial, intelligence  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Helper – silence alert_service.reload_rules in mutation tests
# ---------------------------------------------------------------------------

_SYNC_PATH = "app.api.alert_routes._sync_alert_service"


# ---------------------------------------------------------------------------
# GET /api/alerts/rules – list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules_empty(db_client):
    resp = await db_client.get("/api/alerts/rules")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_rules_returns_created_rule(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        await db_client.post(
            "/api/alerts/rules",
            json={
                "name": "My Rule",
                "condition": "attack_type",
                "target": "DDoS",
                "threshold": None,
                "enabled": True,
            },
        )
    resp = await db_client.get("/api/alerts/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 1
    assert rules[0]["name"] == "My Rule"


# ---------------------------------------------------------------------------
# POST /api/alerts/rules – create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_returns_201(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.post(
            "/api/alerts/rules",
            json={
                "name": "Risk Rule",
                "condition": "risk_above",
                "target": "RU",
                "threshold": 75.0,
                "enabled": True,
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Risk Rule"
    assert body["condition"] == "risk_above"
    assert body["threshold"] == 75.0
    assert "id" in body


@pytest.mark.asyncio
async def test_create_rule_syncs_alert_service(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock) as mock_sync:
        resp = await db_client.post(
            "/api/alerts/rules",
            json={
                "name": "Bbox Rule",
                "condition": "bbox",
                "bbox": "40.0,-74.0,41.0,-73.0",
                "enabled": True,
            },
        )
    assert resp.status_code == 201
    mock_sync.assert_called_once()


@pytest.mark.asyncio
async def test_create_rule_price_change(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.post(
            "/api/alerts/rules",
            json={
                "name": "BTC Spike",
                "condition": "price_change",
                "target": "BTC",
                "threshold": 5.0,
                "enabled": True,
            },
        )
    assert resp.status_code == 201
    assert resp.json()["condition"] == "price_change"


# ---------------------------------------------------------------------------
# DELETE /api/alerts/rules/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rule_returns_204(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "To Delete", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        del_resp = await db_client.delete(f"/api/alerts/rules/{rule_id}")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_rule_not_found_returns_404(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.delete("/api/alerts/rules/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_from_list(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Ephemeral", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        await db_client.delete(f"/api/alerts/rules/{rule_id}")

    resp = await db_client.get("/api/alerts/rules")
    ids = [r["id"] for r in resp.json()]
    assert rule_id not in ids


# ---------------------------------------------------------------------------
# PUT /api/alerts/rules/{id} – update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rule_name(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Old Name", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.put(
            f"/api/alerts/rules/{rule_id}", json={"name": "New Name"}
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_rule_enabled_false(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Toggle Me", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.put(
            f"/api/alerts/rules/{rule_id}", json={"enabled": False}
        )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_update_rule_threshold(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={
                "name": "Risk Rule",
                "condition": "risk_above",
                "threshold": 50.0,
                "enabled": True,
            },
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.put(
            f"/api/alerts/rules/{rule_id}", json={"threshold": 80.0}
        )
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 80.0


@pytest.mark.asyncio
async def test_update_rule_target_and_bbox(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Geo", "condition": "bbox", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.put(
            f"/api/alerts/rules/{rule_id}",
            json={"target": "US", "bbox": "30.0,-90.0,50.0,-70.0"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target"] == "US"
    assert body["bbox"] == "30.0,-90.0,50.0,-70.0"


@pytest.mark.asyncio
async def test_update_rule_not_found_returns_404(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.put(
            "/api/alerts/rules/99999", json={"name": "Ghost"}
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/alerts/rules/{id}/toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_rule_flips_enabled(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Flipper", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]
    original_enabled = create_resp.json()["enabled"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.patch(f"/api/alerts/rules/{rule_id}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is not original_enabled


@pytest.mark.asyncio
async def test_toggle_rule_twice_restores_state(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        create_resp = await db_client.post(
            "/api/alerts/rules",
            json={"name": "Double Flip", "condition": "attack_type", "enabled": True},
        )
    rule_id = create_resp.json()["id"]

    with patch(_SYNC_PATH, new_callable=AsyncMock):
        await db_client.patch(f"/api/alerts/rules/{rule_id}/toggle")
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.patch(f"/api/alerts/rules/{rule_id}/toggle")
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_toggle_rule_not_found_returns_404(db_client):
    with patch(_SYNC_PATH, new_callable=AsyncMock):
        resp = await db_client.patch("/api/alerts/rules/99999/toggle")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _sync_alert_service – exception is swallowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_alert_service_exception_swallowed_internally():
    """_sync_alert_service itself swallows errors from reload_rules."""
    from app.api.alert_routes import _sync_alert_service

    mock_session = AsyncMock()
    # Make db.execute raise to trigger the except block
    mock_session.execute = AsyncMock(side_effect=RuntimeError("db gone"))
    # Should not raise
    await _sync_alert_service(mock_session)


# ---------------------------------------------------------------------------
# Direct unit tests for route functions (bypass HTTP/ASGI to improve coverage
# tracking of lines after `await` in async SQLAlchemy handlers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules_direct_empty():
    """Directly call list_rules with a mock session returning empty results."""
    from unittest.mock import MagicMock

    from app.api.alert_routes import list_rules

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await list_rules(db=mock_db)
    assert result == []


@pytest.mark.asyncio
async def test_list_rules_direct_with_rules():
    """Directly call list_rules with a mock session returning rules."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from app.api.alert_routes import list_rules
    from app.models.alert import AlertRule

    rule = AlertRule(
        id=1,
        name="Test Rule",
        condition="attack_type",
        target="DDoS",
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [rule]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await list_rules(db=mock_db)
    assert len(result) == 1
    assert result[0].name == "Test Rule"


@pytest.mark.asyncio
async def test_create_rule_direct():
    """Directly call create_rule with a mock session."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock, call

    from app.api.alert_routes import create_rule
    from app.models.alert import AlertRule, AlertRuleCreate

    body = AlertRuleCreate(name="Direct Rule", condition="attack_type", enabled=True)

    # The rule that gets persisted and refreshed
    created_rule = AlertRule(
        id=42,
        name="Direct Rule",
        condition="attack_type",
        target=None,
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    # After refresh, the rule object is populated
    async def fake_refresh(obj):
        obj.id = 42

    mock_db.refresh.side_effect = fake_refresh

    # _sync_alert_service also calls db.execute
    sync_result = MagicMock()
    sync_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=sync_result)

    with patch("app.api.alert_routes._sync_alert_service", new_callable=AsyncMock):
        # We need to make sure the rule gets an id attribute for model_validate
        with patch("app.api.alert_routes.AlertRule") as MockRule:
            MockRule.return_value = created_rule
            result = await create_rule(body=body, db=mock_db)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_rule_direct_found():
    """Directly call delete_rule with a rule that exists."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from app.api.alert_routes import delete_rule
    from app.models.alert import AlertRule

    existing_rule = AlertRule(
        id=5,
        name="Delete Me",
        condition="attack_type",
        target=None,
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_rule

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.delete = AsyncMock()

    with patch("app.api.alert_routes._sync_alert_service", new_callable=AsyncMock):
        await delete_rule(rule_id=5, db=mock_db)

    mock_db.delete.assert_called_once_with(existing_rule)


@pytest.mark.asyncio
async def test_delete_rule_direct_not_found():
    """Directly call delete_rule with a rule that does NOT exist."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from app.api.alert_routes import delete_rule

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await delete_rule(rule_id=99, db=mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_rule_direct_found():
    """Directly call update_rule with a rule that exists."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from app.api.alert_routes import update_rule, AlertRuleUpdate
    from app.models.alert import AlertRule

    existing_rule = AlertRule(
        id=7,
        name="Old Name",
        condition="attack_type",
        target=None,
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_rule

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    body = AlertRuleUpdate(name="New Name", enabled=False, threshold=75.0)

    with patch("app.api.alert_routes._sync_alert_service", new_callable=AsyncMock):
        result = await update_rule(rule_id=7, body=body, db=mock_db)

    assert existing_rule.name == "New Name"
    assert existing_rule.enabled is False
    assert existing_rule.threshold == 75.0


@pytest.mark.asyncio
async def test_update_rule_direct_not_found():
    """Directly call update_rule when rule doesn't exist."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from app.api.alert_routes import update_rule, AlertRuleUpdate

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    body = AlertRuleUpdate(name="Ghost")

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(rule_id=99, body=body, db=mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_toggle_rule_direct_found():
    """Directly call toggle_rule with a rule that exists."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from app.api.alert_routes import toggle_rule
    from app.models.alert import AlertRule

    existing_rule = AlertRule(
        id=3,
        name="Toggle Me",
        condition="attack_type",
        target=None,
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_rule

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    with patch("app.api.alert_routes._sync_alert_service", new_callable=AsyncMock):
        result = await toggle_rule(rule_id=3, db=mock_db)

    assert existing_rule.enabled is False  # was True, now toggled


@pytest.mark.asyncio
async def test_toggle_rule_direct_not_found():
    """Directly call toggle_rule when rule doesn't exist."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from app.api.alert_routes import toggle_rule

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await toggle_rule(rule_id=999, db=mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_sync_alert_service_direct_success():
    """_sync_alert_service should reload rules from DB."""
    from unittest.mock import MagicMock

    from app.api.alert_routes import _sync_alert_service

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.services.alert_service.alert_service.reload_rules", new_callable=AsyncMock
    ):
        await _sync_alert_service(mock_db)

    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_rule_direct_target_and_bbox():
    """Update target and bbox fields (lines 106, 108)."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from app.api.alert_routes import update_rule, AlertRuleUpdate
    from app.models.alert import AlertRule

    existing_rule = AlertRule(
        id=8,
        name="Geo Rule",
        condition="bbox",
        target=None,
        threshold=None,
        bbox=None,
        enabled=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_rule

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    body = AlertRuleUpdate(target="US", bbox="30.0,-90.0,50.0,-70.0")

    with patch("app.api.alert_routes._sync_alert_service", new_callable=AsyncMock):
        await update_rule(rule_id=8, body=body, db=mock_db)

    assert existing_rule.target == "US"
    assert existing_rule.bbox == "30.0,-90.0,50.0,-70.0"
