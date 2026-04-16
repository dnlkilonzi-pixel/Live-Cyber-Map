"""Attack event ORM model and Pydantic schemas."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class AttackType(str, enum.Enum):
    DDoS = "DDoS"
    Malware = "Malware"
    Phishing = "Phishing"
    Ransomware = "Ransomware"
    Intrusion = "Intrusion"
    BruteForce = "BruteForce"
    SQLInjection = "SQLInjection"
    XSS = "XSS"
    ZeroDay = "ZeroDay"


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class AttackEvent(Base):
    """Persisted record of a single cyber attack event."""

    __tablename__ = "attack_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source
    source_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    source_country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_lat: Mapped[float] = mapped_column(Float, nullable=False)
    source_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # Destination
    dest_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    dest_country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # Attack metadata
    attack_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AttackEventCreate(BaseModel):
    """Schema for creating a new AttackEvent (inbound)."""

    source_ip: str
    dest_ip: str
    source_country: str
    dest_country: str
    source_lat: float
    source_lng: float
    dest_lat: float
    dest_lng: float
    attack_type: AttackType
    severity: int
    cluster_id: Optional[str] = None
    timestamp: Optional[datetime] = None


class AttackEventResponse(BaseModel):
    """Schema for returning an AttackEvent to API consumers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_ip: str
    dest_ip: str
    source_country: str
    dest_country: str
    source_lat: float
    source_lng: float
    dest_lat: float
    dest_lng: float
    attack_type: str
    severity: int
    cluster_id: Optional[str]
    timestamp: datetime
