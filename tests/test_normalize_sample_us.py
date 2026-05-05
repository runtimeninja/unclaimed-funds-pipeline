"""Tests for the bundled sample US unclaimed-property source.

Two layers:
  * Pure unit tests for the source-local helpers.
  * One end-to-end test that ingests the real ``data/sample_us_unclaimed.csv``
    through the runner and asserts the shape of the normalized output —
    including dedup behaviour against the three deliberate duplicate rows.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

from db.models import EntityType, NormalizedRecord, RawRecord
from db.session import get_session
from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester
from normalize.runner import run_normalize
from normalize.sources.sample_us import (
    SampleUSNormalizer,
    coerce_amount_text,
    find_name_keywords,
)


SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_us_unclaimed.csv"


# --- coerce_amount_text -----------------------------------------------------


def test_coerce_amount_text_passes_clean_numbers_through():
    assert coerce_amount_text("3247.55") == "3247.55"
    assert coerce_amount_text("  100.00 ") == "100.00"


def test_coerce_amount_text_handles_dollar_and_commas():
    # The shared parser will strip $ and , later; we only need to leave a
    # parseable fragment alone here.
    assert coerce_amount_text("$1,250.75") == "$1,250.75"


def test_coerce_amount_text_returns_none_for_blank():
    assert coerce_amount_text(None) is None
    assert coerce_amount_text("") is None
    assert coerce_amount_text("   ") is None


def test_coerce_amount_text_extracts_lower_bound_from_at_least():
    assert coerce_amount_text("AMOUNT INDICATED IS AT LEAST $100.00") == "100.00"
    assert coerce_amount_text("AT LEAST $50") == "50"


def test_coerce_amount_text_extracts_lower_bound_from_between():
    assert coerce_amount_text("BETWEEN $50.00 AND $99.99") == "50.00"
    assert coerce_amount_text("between $1,000 and $5,000") == "1,000"


# --- find_name_keywords -----------------------------------------------------


def test_find_name_keywords_empty_for_plain_individual():
    assert find_name_keywords("ALICE SMITH") == []
    assert find_name_keywords(None) == []


def test_find_name_keywords_finds_estate():
    assert find_name_keywords("ESTATE OF JOHN DOE") == ["estate"]


def test_find_name_keywords_finds_trust():
    assert find_name_keywords("WILLIAMS FAMILY TRUST") == ["trust"]


def test_find_name_keywords_finds_multiple():
    # Contrived but exercises the list ordering.
    found = find_name_keywords("HEIR OF DECEASED ESTATE")
    assert set(found) == {"heir", "deceased", "estate"}


# --- SampleUSNormalizer.extract --------------------------------------------


def test_extract_maps_all_fields():
    norm = SampleUSNormalizer()
    fields = norm.extract({
        "property_id": "TX-2024-000001",
        "owner_name": "John Smith",
        "owner_address": "1428 Westheimer Rd",
        "owner_city": "Houston",
        "owner_state": "TX",
        "owner_zip": "77006",
        "claim_amount": "3247.55",
        "property_type_code": "AC01",
        "property_type_description": "Checking Accounts",
        "holder_name": "Wells Fargo Bank NA",
        "reported_year": "2024",
    })
    assert fields.owner_name == "John Smith"
    assert fields.address_line1 == "1428 Westheimer Rd"
    assert fields.city == "Houston"
    assert fields.state == "TX"
    assert fields.zip == "77006"
    assert fields.claim_amount_text == "3247.55"
    assert fields.property_type == "Checking Accounts"
    assert fields.keywords_found == []


def test_extract_handles_estate_keyword():
    norm = SampleUSNormalizer()
    fields = norm.extract({
        "owner_name": "ESTATE OF JAMES PATTERSON",
        "claim_amount": "21500.00",
    })
    assert fields.keywords_found == ["estate"]


def test_extract_handles_range_amount():
    norm = SampleUSNormalizer()
    fields = norm.extract({
        "owner_name": "Diane Cooper",
        "claim_amount": "AMOUNT INDICATED IS AT LEAST $100.00",
    })
    assert fields.claim_amount_text == "100.00"


def test_extract_tolerates_missing_keys():
    norm = SampleUSNormalizer()
    fields = norm.extract({"owner_name": "John Smith"})
    assert fields.owner_name == "John Smith"
    assert fields.address_line1 is None
    assert fields.city is None
    assert fields.claim_amount_text is None


# --- End-to-end: ingest the real CSV and normalize -------------------------


def test_sample_us_csv_round_trip():
    """Ingest data/sample_us_unclaimed.csv and verify the normalized shape."""
    test_source = f"sample_us_test_{uuid.uuid4().hex[:8]}"

    ingester = CSVFileIngester(path=SAMPLE_CSV, source=test_source)
    ingest_result = run_ingest(ingester)

    try:
        # 73 rows in the CSV.
        assert ingest_result.count == 73

        result = run_normalize({test_source: SampleUSNormalizer()})

        # 3 deliberate duplicates → 70 unique normalized records.
        assert result.processed == 70
        assert result.skipped_duplicate == 3

        with get_session() as session:
            rows = session.scalars(
                select(NormalizedRecord)
                .join(RawRecord, NormalizedRecord.raw_record_id == RawRecord.id)
                .where(RawRecord.file_batch_id == ingest_result.file_batch_id)
            ).all()
            assert len(rows) == 70

            by_name = {r.owner_name_normalized: r for r in rows}

            # Individual: amount + entity_type + state uppercased.
            john = by_name["JOHN SMITH"]
            assert john.entity_type == EntityType.individual
            assert john.claim_amount == Decimal("3247.55")
            assert john.state == "TX"
            assert john.city == "Houston"

            # Business: LLC marker → business.
            lonestar = by_name["LONESTAR HOLDINGS LLC"]
            assert lonestar.entity_type == EntityType.business
            assert lonestar.claim_amount == Decimal("87420.00")

            # Estate: prefix → estate, plus 'estate' keyword captured.
            patterson = by_name["ESTATE OF JAMES PATTERSON"]
            assert patterson.entity_type == EntityType.estate
            assert patterson.claim_amount == Decimal("21500.00")
            assert "estate" in patterson.keywords_found

            # Trust: shared parser maps trusts onto estate for outreach purposes.
            williams_trust = by_name["WILLIAMS FAMILY TRUST"]
            assert williams_trust.entity_type == EntityType.estate
            assert "trust" in williams_trust.keywords_found

            # Range-description amount: lower bound parsed.
            cooper = by_name["DIANE COOPER"]
            assert cooper.claim_amount == Decimal("100.00")

            # $1,250.75 with commas: shared parser strips them.
            obrien = by_name["KATHLEEN O'BRIEN"]
            assert obrien.claim_amount == Decimal("1250.75")

            # Blank amount: stays None.
            henderson = by_name["WALTER HENDERSON"]
            assert henderson.claim_amount is None

        # Idempotency: re-running normalize creates no new normalized rows.
        # The 3 duplicate raw rows still have no normalized child, so the
        # selection picks them up again and the dedup hash skips them again.
        rerun = run_normalize({test_source: SampleUSNormalizer()})
        assert rerun.processed == 0
        assert rerun.skipped_duplicate == 3
        assert rerun.total_seen == 3
    finally:
        with get_session() as session:
            session.execute(
                delete(RawRecord).where(
                    RawRecord.file_batch_id == ingest_result.file_batch_id
                )
            )
