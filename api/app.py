"""FastAPI app exposing scored leads to the bundled dashboard.

Read-only. No auth — bind to 127.0.0.1 only. Routes:

  GET /api/leads               paginated list, with priority/state/min_amount filters
  GET /api/leads/{id}          single lead with score breakdown
  GET /api/stats               counts by priority, total amount, export status

The single-file HTML dashboard at `frontend/index.html` is mounted at `/`.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import LeadDetail, LeadListResponse, LeadSummary, StatsResponse
from db.models import NormalizedRecord, Priority, ScoredLead
from db.session import SessionLocal


_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def get_db() -> Session:
    """Per-request DB session. No commit — the API is read-only."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="UFIP API",
        description="Read-only access to scored unclaimed-funds leads.",
        version="0.1.0",
    )

    @app.get("/api/leads", response_model=LeadListResponse)
    def list_leads(
        priority: Priority | None = Query(None),
        state: str | None = Query(None, max_length=8),
        min_amount: Decimal | None = Query(None, ge=0),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ) -> LeadListResponse:
        filters = []
        if priority is not None:
            filters.append(ScoredLead.priority == priority)
        if state:
            filters.append(NormalizedRecord.state == state.upper())
        if min_amount is not None:
            filters.append(NormalizedRecord.claim_amount >= min_amount)

        base = (
            select(ScoredLead, NormalizedRecord)
            .join(NormalizedRecord, ScoredLead.normalized_record_id == NormalizedRecord.id)
        )
        for f in filters:
            base = base.where(f)

        total = db.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        ) or 0

        rows = db.execute(
            base.order_by(ScoredLead.score.desc(), ScoredLead.id)
            .limit(limit)
            .offset(offset)
        ).all()

        items = [
            LeadSummary(
                id=scored.id,
                owner_name=normalized.owner_name_normalized,
                entity_type=normalized.entity_type,
                city=normalized.city,
                state=normalized.state,
                claim_amount=normalized.claim_amount,
                score=scored.score,
                priority=scored.priority,
                exported_to_crm=scored.exported_to_crm,
            )
            for scored, normalized in rows
        ]
        return LeadListResponse(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/leads/{lead_id}", response_model=LeadDetail)
    def get_lead(lead_id: UUID, db: Session = Depends(get_db)) -> LeadDetail:
        row = db.execute(
            select(ScoredLead, NormalizedRecord)
            .join(NormalizedRecord, ScoredLead.normalized_record_id == NormalizedRecord.id)
            .where(ScoredLead.id == lead_id)
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        scored, normalized = row
        return LeadDetail(
            id=scored.id,
            owner_name=normalized.owner_name_normalized,
            entity_type=normalized.entity_type,
            address_line1=normalized.address_line1,
            city=normalized.city,
            state=normalized.state,
            zip=normalized.zip,
            claim_amount=normalized.claim_amount,
            property_type=normalized.property_type,
            keywords_found=list(normalized.keywords_found or []),
            source=normalized.source,
            score=scored.score,
            priority=scored.priority,
            score_breakdown=dict(scored.score_breakdown or {}),
            exported_to_crm=scored.exported_to_crm,
            created_at=scored.created_at,
        )

    @app.get("/api/stats", response_model=StatsResponse)
    def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
        total = db.scalar(select(func.count(ScoredLead.id))) or 0
        by_priority_rows = db.execute(
            select(ScoredLead.priority, func.count(ScoredLead.id))
            .group_by(ScoredLead.priority)
        ).all()
        by_priority = {p.value: 0 for p in Priority}
        for prio, n in by_priority_rows:
            by_priority[prio.value] = n

        total_amount = db.scalar(
            select(func.coalesce(func.sum(NormalizedRecord.claim_amount), 0))
            .join(ScoredLead, ScoredLead.normalized_record_id == NormalizedRecord.id)
        ) or Decimal("0")

        exported = db.scalar(
            select(func.count(ScoredLead.id)).where(ScoredLead.exported_to_crm.is_(True))
        ) or 0

        return StatsResponse(
            total_leads=total,
            by_priority=by_priority,
            total_claim_amount=total_amount,
            exported=exported,
            pending_export=total - exported,
        )

    if _FRONTEND_DIR.is_dir():
        # Mount last so /api/* routes win.
        app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
