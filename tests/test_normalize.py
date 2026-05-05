"""End-to-end normalization test: ingest CSV -> normalize -> assert.

Hits the dev database. Uses a unique source per run so it can't collide
with any other state in `raw_records` / `normalized_records`. FK ondelete=
CASCADE means deleting the raw rows tears down the normalized rows too.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from db.models import EntityType, NormalizedRecord, RawRecord
from db.session import get_session
from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester
from normalize.base import BaseNormalizer, RawFields
from normalize.runner import run_normalize


class _FixtureNormalizer(BaseNormalizer):
    """Mapper for the fixture CSV shape used in this test."""

    def __init__(self, source: str) -> None:
        self.source = source

    def extract(self, raw: dict[str, Any]) -> RawFields:
        return RawFields(
            owner_name=raw.get("owner_name"),
            city=raw.get("city"),
            state=raw.get("state"),
            claim_amount_text=raw.get("claim_amount"),
        )


def test_normalize_round_trip(tmp_path):
    test_source = f"test_csv_{uuid.uuid4().hex[:8]}"
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "owner_name,city,state,claim_amount\n"
        "Alice Smith,Boston,MA,1234.56\n"
        "ACME LLC,Buffalo,ny,$12.00\n"
        "ESTATE OF JOHN DOE,Albany,NY,\n"
        "Bob Jones, Brooklyn ,NY,\"9,999.00\"\n",
        encoding="utf-8",
    )

    ingester = CSVFileIngester(path=csv_path, source=test_source)
    ingest_result = run_ingest(ingester)
    normalizer = _FixtureNormalizer(source=test_source)

    try:
        assert ingest_result.count == 4

        result = run_normalize({test_source: normalizer})
        assert result.processed == 4
        assert result.skipped_duplicate == 0

        with get_session() as session:
            rows = session.scalars(
                select(NormalizedRecord)
                .join(RawRecord, NormalizedRecord.raw_record_id == RawRecord.id)
                .where(RawRecord.file_batch_id == ingest_result.file_batch_id)
            ).all()
            assert len(rows) == 4

            by_name = {r.owner_name_normalized: r for r in rows}

            alice = by_name["ALICE SMITH"]
            assert alice.entity_type == EntityType.individual
            assert alice.claim_amount == Decimal("1234.56")
            assert alice.state == "MA"
            assert alice.dedup_hash is not None
            assert len(alice.dedup_hash) == 64

            acme = by_name["ACME LLC"]
            assert acme.entity_type == EntityType.business
            assert acme.claim_amount == Decimal("12.00")
            assert acme.state == "NY"  # uppercased from 'ny'

            estate = by_name["ESTATE OF JOHN DOE"]
            assert estate.entity_type == EntityType.estate
            assert estate.claim_amount is None  # blank cell -> None

            bob = by_name["BOB JONES"]
            assert bob.entity_type == EntityType.individual
            assert bob.claim_amount == Decimal("9999.00")
            assert bob.city == "Brooklyn"  # whitespace trimmed

        # Idempotency: re-running must not double-process our records.
        rerun = run_normalize({test_source: normalizer})
        assert rerun.processed == 0
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == ingest_result.file_batch_id
                )
            )
