"""End-to-end test for the Airtable export.

Uses a fake AirtableClient so the test never touches the real API. The
fixture flow ingests CSV -> normalizes -> scores -> exports, then verifies
that scored_leads were marked exported with the right airtable_record_id.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select

from crm.runner import run_export
from db.models import NormalizedRecord, RawRecord, ScoredLead
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


class _FakeAirtableClient:
    """Test double matching the AirtableClient protocol."""

    def __init__(self) -> None:
        self.batches_received: list[list[dict]] = []

    def create_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.batches_received.append(records)
        return [
            {"id": f"recFAKE{uuid.uuid4().hex[:10]}", "fields": r}
            for r in records
        ]


class _AlwaysFailingClient:
    """Test double that simulates a permanent Airtable outage."""

    def create_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise RuntimeError("Simulated Airtable outage")


def _seed_pipeline(tmp_path, source: str):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "owner_name,city,state,claim_amount\n"
        "ESTATE OF JANE DOE,NYC,NY,50000.00\n"
        "ACME LLC,Boston,MA,1500.00\n"
        "Bob Jones,Buffalo,NY,5.00\n",
        encoding="utf-8",
    )
    ingest_result = run_ingest(CSVFileIngester(path=csv_path, source=source))
    run_normalize({source: _FixtureNormalizer(source=source)})
    run_score()
    return ingest_result


def _our_scored_leads(session, file_batch_id):
    return session.scalars(
        select(ScoredLead)
        .join(NormalizedRecord, ScoredLead.normalized_record_id == NormalizedRecord.id)
        .join(RawRecord, NormalizedRecord.raw_record_id == RawRecord.id)
        .where(RawRecord.file_batch_id == file_batch_id)
    ).all()


def test_export_round_trip_marks_records_with_airtable_id(tmp_path):
    test_source = f"test_export_{uuid.uuid4().hex[:8]}"
    ingest_result = _seed_pipeline(tmp_path, test_source)

    try:
        client = _FakeAirtableClient()
        result = run_export(client=client, batch_size=2)

        assert result.exported >= 3
        assert result.failed == 0

        # The fake client must have received our records (mixed in with any
        # other un-exported leads in the dev DB).
        names_pushed = {
            r["Name"] for batch in client.batches_received for r in batch
        }
        assert {"ESTATE OF JANE DOE", "ACME LLC", "BOB JONES"} <= names_pushed

        with get_session() as session:
            scored = _our_scored_leads(session, ingest_result.file_batch_id)
            assert len(scored) == 3
            for s in scored:
                assert s.exported_to_crm is True
                assert s.airtable_record_id is not None
                assert s.airtable_record_id.startswith("recFAKE")
                assert s.exported_at is not None

        # Re-running must not re-push any of our records.
        client2 = _FakeAirtableClient()
        run_export(client=client2, batch_size=2)
        names_pushed_again = {
            r["Name"] for batch in client2.batches_received for r in batch
        }
        assert "ESTATE OF JANE DOE" not in names_pushed_again
        assert "ACME LLC" not in names_pushed_again
        assert "BOB JONES" not in names_pushed_again
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == ingest_result.file_batch_id
                )
            )


def test_export_does_not_mark_records_when_airtable_fails(tmp_path):
    test_source = f"test_export_fail_{uuid.uuid4().hex[:8]}"
    ingest_result = _seed_pipeline(tmp_path, test_source)

    try:
        client = _AlwaysFailingClient()
        result = run_export(client=client, batch_size=2)

        # Our 3 records contributed at least 3 to `failed`; other unexported
        # rows in the dev DB may also be in the count.
        assert result.exported == 0
        assert result.failed >= 3

        with get_session() as session:
            scored = _our_scored_leads(session, ingest_result.file_batch_id)
            assert len(scored) == 3
            for s in scored:
                assert s.exported_to_crm is False
                assert s.airtable_record_id is None
                assert s.exported_at is None
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == ingest_result.file_batch_id
                )
            )
