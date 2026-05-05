"""Drive scoring across all normalized_records that aren't yet scored.

Selection: any normalized record without a scored_leads child. The DB-side
unique constraint on `scored_leads.normalized_record_id` is a safety net —
the selection already prevents re-scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select

from db.models import NormalizedRecord, Priority, ScoredLead
from db.session import get_session
from score.rules import apply_rules, load_config


@dataclass(frozen=True)
class ScoreSummary:
    processed: int
    by_priority: dict[str, int] = field(default_factory=dict)


def run_score(
    *,
    config_path: Path | str | None = None,
    config: dict[str, Any] | None = None,
    flush_every: int = 500,
) -> ScoreSummary:
    """Score every un-scored normalized record. Pass either `config` or `config_path`."""
    if config is None:
        config = load_config(config_path)

    by_priority = {Priority.high.value: 0, Priority.medium.value: 0, Priority.low.value: 0}
    processed = 0

    stmt = (
        select(NormalizedRecord)
        .outerjoin(ScoredLead, ScoredLead.normalized_record_id == NormalizedRecord.id)
        .where(ScoredLead.id.is_(None))
        .order_by(NormalizedRecord.created_at)
    )

    with get_session() as session:
        for record in session.scalars(stmt).yield_per(flush_every):
            result = apply_rules(record, config)
            session.add(
                ScoredLead(
                    normalized_record_id=record.id,
                    score=result.score,
                    priority=result.priority,
                    score_breakdown=result.breakdown,
                )
            )
            by_priority[result.priority.value] += 1
            processed += 1

            if processed % flush_every == 0:
                session.flush()

    logger.success(
        f"Score done: processed={processed} "
        f"high={by_priority[Priority.high.value]} "
        f"medium={by_priority[Priority.medium.value]} "
        f"low={by_priority[Priority.low.value]}"
    )
    return ScoreSummary(processed=processed, by_priority=by_priority)
