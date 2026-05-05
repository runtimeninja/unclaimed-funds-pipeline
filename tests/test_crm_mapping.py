"""Unit tests for the Airtable field-mapping function."""
from __future__ import annotations

import json
from decimal import Decimal

from crm.mapping import build_airtable_fields
from db.models import EntityType, NormalizedRecord, Priority, ScoredLead


def _normalized(**overrides) -> NormalizedRecord:
    defaults = dict(
        owner_name_normalized="ALICE SMITH",
        entity_type=EntityType.individual,
        address_line1="1 MAIN ST",
        city="Boston",
        state="MA",
        zip="02101",
        claim_amount=Decimal("1234.56"),
        property_type=None,
        record_age_years=None,
        keywords_found=[],
        source="ny_csv",
    )
    defaults.update(overrides)
    return NormalizedRecord(**defaults)


def _scored(**overrides) -> ScoredLead:
    defaults = dict(
        score=72,
        priority=Priority.high,
        score_breakdown={"total": 72, "amount_tier": {"matched": "tier_1k", "points": 10}},
        exported_to_crm=False,
    )
    defaults.update(overrides)
    return ScoredLead(**defaults)


def test_build_fields_basic_record():
    fields = build_airtable_fields(_scored(), _normalized())

    assert fields["Name"] == "ALICE SMITH"
    assert fields["Entity Type"] == "individual"
    assert fields["Address Line 1"] == "1 MAIN ST"
    assert fields["City"] == "Boston"
    assert fields["State"] == "MA"
    assert fields["Zip"] == "02101"
    assert fields["Claim Amount"] == 1234.56
    assert fields["Source"] == "ny_csv"
    assert fields["Priority"] == "high"
    assert fields["Score"] == 72

    breakdown = json.loads(fields["Score Breakdown"])
    assert breakdown["total"] == 72


def test_build_fields_handles_none_claim_amount():
    fields = build_airtable_fields(_scored(), _normalized(claim_amount=None))
    assert fields["Claim Amount"] is None


def test_build_fields_handles_none_address_components():
    fields = build_airtable_fields(
        _scored(),
        _normalized(address_line1=None, city=None, state=None, zip=None),
    )
    assert fields["Address Line 1"] is None
    assert fields["City"] is None
    assert fields["State"] is None
    assert fields["Zip"] is None


def test_build_fields_serializes_breakdown_with_default_str():
    # Breakdown may contain types JSON can't natively serialize (Decimal,
    # datetime). default=str must keep build_airtable_fields from crashing.
    fields = build_airtable_fields(
        _scored(score_breakdown={"raw_amount": Decimal("1.50")}),
        _normalized(),
    )
    payload = json.loads(fields["Score Breakdown"])
    assert payload["raw_amount"] == "1.50"


def test_build_fields_uses_priority_enum_value():
    fields = build_airtable_fields(_scored(priority=Priority.medium), _normalized())
    assert fields["Priority"] == "medium"


def test_build_fields_uses_entity_type_enum_value():
    fields = build_airtable_fields(_scored(), _normalized(entity_type=EntityType.estate))
    assert fields["Entity Type"] == "estate"
