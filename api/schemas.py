"""Pydantic response schemas for the read-only API.

Each schema corresponds to one shape we hand back over the wire. We deliberately
flatten the (ScoredLead, NormalizedRecord) join so the frontend doesn't have to
chase nested relationships — score and lead identity arrive as one object.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from db.models import EntityType, Priority


class LeadSummary(BaseModel):
    """Row-level shape for `/api/leads` lists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str | None
    entity_type: EntityType
    city: str | None
    state: str | None
    claim_amount: Decimal | None
    score: int
    priority: Priority
    exported_to_crm: bool


class LeadDetail(LeadSummary):
    """Single-lead shape, including address parts and the score breakdown."""

    address_line1: str | None
    zip: str | None
    property_type: str | None
    keywords_found: list[str]
    source: str
    score_breakdown: dict[str, Any]
    created_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadSummary]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    total_leads: int
    by_priority: dict[str, int]      # {"high": N, "medium": N, "low": N}
    total_claim_amount: Decimal
    exported: int
    pending_export: int
