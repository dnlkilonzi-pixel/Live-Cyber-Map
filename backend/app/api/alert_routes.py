"""Alert rules REST API – CRUD for user-defined notification rules."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import (
    AlertRule,
    AlertRuleCreate,
    AlertRuleResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AlertRuleUpdate(BaseModel):
    """Partial update payload for PUT /rules/{id}."""

    name: Optional[str] = None
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    target: Optional[str] = None
    bbox: Optional[str] = None


@router.get(
    "/rules",
    response_model=List[AlertRuleResponse],
    tags=["alerts"],
    summary="List all alert rules",
)
async def list_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))
    rules = result.scalars().all()
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/rules",
    response_model=AlertRuleResponse,
    tags=["alerts"],
    summary="Create a new alert rule",
    status_code=201,
)
async def create_rule(body: AlertRuleCreate, db: AsyncSession = Depends(get_db)):
    rule = AlertRule(
        name=body.name,
        condition=body.condition.value,
        target=body.target,
        threshold=body.threshold,
        bbox=body.bbox,
        enabled=body.enabled,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    # Sync in-memory cache
    await _sync_alert_service(db)
    return AlertRuleResponse.model_validate(rule)


@router.delete(
    "/rules/{rule_id}",
    tags=["alerts"],
    summary="Delete an alert rule",
    status_code=204,
)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await db.delete(rule)
    await _sync_alert_service(db)


@router.put(
    "/rules/{rule_id}",
    response_model=AlertRuleResponse,
    tags=["alerts"],
    summary="Update an alert rule in-place (rename, enable/disable, change threshold/bbox)",
)
async def update_rule(
    rule_id: int, body: AlertRuleUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    if body.name is not None:
        rule.name = body.name
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.threshold is not None:
        rule.threshold = body.threshold
    if body.target is not None:
        rule.target = body.target
    if body.bbox is not None:
        rule.bbox = body.bbox
    await db.flush()
    await db.refresh(rule)
    await _sync_alert_service(db)
    return AlertRuleResponse.model_validate(rule)


@router.patch(
    "/rules/{rule_id}/toggle",
    response_model=AlertRuleResponse,
    tags=["alerts"],
    summary="Toggle a rule on/off",
)
async def toggle_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    rule.enabled = not rule.enabled
    await db.flush()
    await _sync_alert_service(db)
    return AlertRuleResponse.model_validate(rule)


async def _sync_alert_service(db: AsyncSession) -> None:
    """Reload in-memory rule cache after any mutation."""
    try:
        from app.services.alert_service import alert_service

        result = await db.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
        rules = list(result.scalars().all())
        await alert_service.reload_rules(rules)
    except Exception as exc:
        logger.warning("Failed to sync alert service: %s", exc)
