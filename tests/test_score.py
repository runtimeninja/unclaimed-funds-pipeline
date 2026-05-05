"""End-to-end test: ingest CSV -> normalize -> score.

Hits the dev database. Uses a unique source per run; FK ondelete=CASCADE
tears scored_leads + normalized_records down with the parent raw rows.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select

from db.models import NormalizedRecord, Priority, RawRecord, ScoredLead
from db.session import get_session
from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester
from normalize.base import BaseNormalizer, RawFields
from normalize.runner import run_normalize
from score.runner import run_score


class _FixtureNormalizer(BaseNormalizer):
    def __init__(self, source: str) -> None:
        self.source = source

    def extract(self, raw: dict[str, Any]) -> RawFields:
        return RawFields(
            owner_name=raw.get("owner_name"),
            city=raw.get("city"),
            state=raw.get("state"),
            claim_amount_text=raw.get("claim_amount"),
        )


def test_score_round_trip(tmp_path):
    test_source = f"test_score_{uuid.uuid4().hex[:8]}"
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "owner_name,city,state,claim_amount\n"
        "ESTATE OF JANE DOE,NYC,NY,50000.00\n"     # high: tier_25k+estate+addr
        "ACME LLC,Boston,MA,1500.00\n"              # low/medium: tier_1k+biz+addr
        "Bob Jones,Buffalo,NY,5.00\n",              # low: just individual+addr
        encoding="utf-8",
    )

    ingester = CSVFileIngester(path=csv_path, source=test_source)
    ingest_result = run_ingest(ingester)
    normalizer = _FixtureNormalizer(source=test_source)

    try:
        norm_result = run_normalize({test_source: normalizer})
        assert norm_result.processed == 3

        score_result = run_score()
        # >=3 because other un-scored normalized rows in the dev DB may also
        # land; what we care about is that ours all got scored.
        assert score_result.processed >= 3

        with get_session() as session:
            scored = session.execute(
                select(ScoredLead, NormalizedRecord)
                .join(NormalizedRecord, ScoredLead.normalized_record_id == NormalizedRecord.id)
                .join(RawRecord, NormalizedRecord.raw_record_id == RawRecord.id)
                .where(RawRecord.file_batch_id == ingest_result.file_batch_id)
            ).all()
            assert len(scored) == 3

            by_name = {n.owner_name_normalized: (s, n) for s, n in scored}

            estate_lead, _ = by_name["ESTATE OF JANE DOE"]
            tiny_lead, _ = by_name["BOB JONES"]
            acme_lead, _ = by_name["ACME LLC"]

            # Sanity: scoring must discriminate between obviously different leads.
            assert estate_lead.score > acme_lead.score > tiny_lead.score

            # Estate of $50k with an address should land on `high` under the default config.
            assert estate_lead.priority == Priority.high

            # Defaults aren't exported yet.
            for s, _ in by_name.values():
                assert s.exported_to_crm is False
                assert isinstance(s.score_breakdown, dict)
                assert s.score_breakdown.get("total") == s.score
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == ingest_result.file_batch_id
                )
            )
