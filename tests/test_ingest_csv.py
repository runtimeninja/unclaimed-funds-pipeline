"""Smoke test: CSV -> raw_records via the ingestion scaffold.

Hits the dev database (Docker Postgres on 5433). Each run uses its own
file_batch_id and cleans up after itself, so it can run repeatedly without
leaking rows.
"""
from __future__ import annotations

from sqlalchemy import delete, select

from db.models import RawRecord
from db.session import get_session
from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester


def test_csv_file_ingester_writes_to_raw_records(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "owner_name,city,state,claim_amount\n"
        "Alice Smith,Boston,MA,1234.56\n"
        "Bob Jones,Brooklyn,NY,9999.00\n"
        "ACME LLC,Buffalo,NY,12.00\n",
        encoding="utf-8",
    )

    ingester = CSVFileIngester(path=csv_path, source="test_csv")
    result = run_ingest(ingester)

    try:
        assert result.count == 3

        with get_session() as session:
            rows = session.scalars(
                select(RawRecord).where(
                    RawRecord.file_batch_id == result.file_batch_id
                )
            ).all()
            assert len(rows) == 3
            assert {r.source for r in rows} == {"test_csv"}

            alice = next(r for r in rows if r.raw_data["owner_name"] == "Alice Smith")
            assert alice.raw_data["city"] == "Boston"
            # CSV cells are strings; normalization happens later.
            assert alice.raw_data["claim_amount"] == "1234.56"
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == result.file_batch_id
                )
            )
