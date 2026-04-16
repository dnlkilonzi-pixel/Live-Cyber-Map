"""ORM models for persisting intelligence data (news and country risk).

Tables:
  - news_items              : deduplicated news headlines
  - country_risk_snapshots  : periodic risk score snapshots for trend analysis
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NewsItemDB(Base):
    """Persisted news headline."""

    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # MD5 of URL
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    published_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class CountryRiskSnapshot(Base):
    """Snapshot of a country's risk scores at a point in time (for trend lines)."""

    __tablename__ = "country_risk_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iso2: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    cyber_score: Mapped[float] = mapped_column(Float, nullable=False)
    news_score: Mapped[float] = mapped_column(Float, nullable=False)
    attack_count_24h: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshotted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
