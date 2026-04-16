"""Alert rule ORM model and Pydantic schemas."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AlertCondition(str, enum.Enum):
    RISK_ABOVE = "risk_above"          # country risk_score > threshold
    ATTACK_TYPE = "attack_type"        # attack of specific type detected
    PRICE_CHANGE = "price_change"      # asset price change > threshold %
    BBOX = "bbox"                      # attack destination inside lat/lng bounding box
    ANOMALY_SCORE = "anomaly_score"    # anomaly score exceeds threshold


class AlertRule(Base):
    """A user-defined alert rule stored in PostgreSQL."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    condition: Mapped[str] = mapped_column(String(50), nullable=False)  # AlertCondition value

    # Condition parameters (nullable; which ones apply depends on condition type)
    target: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # country iso2, attack type, or asset symbol
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # numeric threshold
    bbox: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)     # geofence: "lat_min,lng_min,lat_max,lng_max"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AlertRuleCreate(BaseModel):
    name: str
    condition: AlertCondition
    target: Optional[str] = None
    threshold: Optional[float] = None
    bbox: Optional[str] = None
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    condition: str
    target: Optional[str]
    threshold: Optional[float]
    bbox: Optional[str]
    enabled: bool
    created_at: datetime


class AlertFired(BaseModel):
    rule_id: int
    rule_name: str
    condition: str
    message: str
    fired_at: float  # Unix timestamp
