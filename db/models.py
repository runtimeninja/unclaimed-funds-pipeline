"""SQLAlchemy ORM models for the UFIP pipeline.

Three layers:
  raw_records         -- untouched ingested rows (JSONB blob)
  normalized_records  -- cleaned + structured fields, dedup key
  scored_leads        -- final scored output, exported flag for CRM
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base. All models inherit from this."""


class EntityType(str, enum.Enum):
    individual = "individual"
    business = "business"
    estate = "estate"
    unknown = "unknown"


class Priority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class RawRecord(Base):
    __tablename__ = "raw_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    file_batch_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    normalized: Mapped[list["NormalizedRecord"]] = relationship(
        back_populates="raw_record",
        cascade="all, delete-orphan",
    )


class NormalizedRecord(Base):
    __tablename__ = "normalized_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner_name_normalized: Mapped[Optional[str]] = mapped_column(String(512), index=True)
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="entity_type"),
        nullable=False,
        default=EntityType.unknown,
        index=True,
    )

    address_line1: Mapped[Optional[str]] = mapped_column(String(512))
    city: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    state: Mapped[Optional[str]] = mapped_column(String(8))
    zip: Mapped[Optional[str]] = mapped_column(String(16))

    claim_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), index=True)
    property_type: Mapped[Optional[str]] = mapped_column(String(128))
    record_age_years: Mapped[Optional[int]] = mapped_column(Integer)
    keywords_found: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Stable hash over (name, address, claim_amount) used to detect duplicates.
    dedup_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raw_record: Mapped["RawRecord"] = relationship(back_populates="normalized")
    score: Mapped[Optional["ScoredLead"]] = relationship(
        back_populates="normalized_record",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index(
            "ix_normalized_dedup_unique",
            "dedup_hash",
            unique=True,
            postgresql_where=text("dedup_hash IS NOT NULL"),
        ),
    )


class ScoredLead(Base):
    __tablename__ = "scored_leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    normalized_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("normalized_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    priority: Mapped[Priority] = mapped_column(
        SAEnum(Priority, name="priority"),
        nullable=False,
        index=True,
    )
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    exported_to_crm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    airtable_record_id: Mapped[Optional[str]] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    normalized_record: Mapped["NormalizedRecord"] = relationship(back_populates="score")
