"""Unit tests for the shared field parsers (no DB)."""
from __future__ import annotations

from decimal import Decimal

from db.models import EntityType
from normalize.fields import (
    clean_state,
    clean_text,
    clean_zip,
    compute_dedup_hash,
    detect_entity_type,
    normalize_name,
    parse_claim_amount,
    split_address_freeform,
)


# --- normalize_name ---------------------------------------------------------

def test_normalize_name_collapses_whitespace_and_uppercases():
    assert normalize_name("  alice   smith  ") == "ALICE SMITH"


def test_normalize_name_strips_trailing_punctuation():
    assert normalize_name("Alice Smith,") == "ALICE SMITH"
    assert normalize_name("Alice Smith.") == "ALICE SMITH"


def test_normalize_name_returns_none_for_blank():
    assert normalize_name(None) is None
    assert normalize_name("") is None
    assert normalize_name("   ") is None


# --- detect_entity_type -----------------------------------------------------

def test_detect_entity_type_business():
    assert detect_entity_type("ACME LLC") == EntityType.business
    assert detect_entity_type("FOO INC.") == EntityType.business
    assert detect_entity_type("BAR HOLDINGS") == EntityType.business
    assert detect_entity_type("BIG CORP") == EntityType.business


def test_detect_entity_type_estate():
    assert detect_entity_type("ESTATE OF JOHN DOE") == EntityType.estate
    assert detect_entity_type("JOHN DOE TRUST") == EntityType.estate


def test_detect_entity_type_individual():
    assert detect_entity_type("ALICE SMITH") == EntityType.individual
    assert detect_entity_type("BOB JONES") == EntityType.individual


def test_detect_entity_type_unknown_for_blank():
    assert detect_entity_type(None) == EntityType.unknown
    assert detect_entity_type("") == EntityType.unknown


# --- parse_claim_amount -----------------------------------------------------

def test_parse_claim_amount_handles_currency_formats():
    assert parse_claim_amount("1234.56") == Decimal("1234.56")
    assert parse_claim_amount("$1,234.56") == Decimal("1234.56")
    assert parse_claim_amount("  $9,999.00  ") == Decimal("9999.00")
    assert parse_claim_amount("0.00") == Decimal("0.00")


def test_parse_claim_amount_returns_none_for_blank_or_garbage():
    assert parse_claim_amount(None) is None
    assert parse_claim_amount("") is None
    assert parse_claim_amount("   ") is None
    assert parse_claim_amount("not a number") is None


# --- clean_state / clean_zip / clean_text ----------------------------------

def test_clean_state_uppercases_two_letter_codes():
    assert clean_state("ny") == "NY"
    assert clean_state(" wa ") == "WA"
    assert clean_state("CA") == "CA"


def test_clean_state_blank_returns_none():
    assert clean_state(None) is None
    assert clean_state("") is None


def test_clean_zip_passes_through_after_strip():
    assert clean_zip(" 02101 ") == "02101"
    assert clean_zip("02101-1234") == "02101-1234"
    assert clean_zip(None) is None
    assert clean_zip("") is None


def test_clean_text_collapses_whitespace():
    assert clean_text("  hello   world  ") == "hello world"
    assert clean_text(None) is None
    assert clean_text("") is None


# --- compute_dedup_hash -----------------------------------------------------

def test_compute_dedup_hash_is_deterministic():
    h1 = compute_dedup_hash("ALICE SMITH", "1 MAIN ST", Decimal("100.00"))
    h2 = compute_dedup_hash("ALICE SMITH", "1 MAIN ST", Decimal("100.00"))
    assert h1 == h2
    assert len(h1) == 64


def test_compute_dedup_hash_changes_with_amount():
    h1 = compute_dedup_hash("ALICE SMITH", "1 MAIN ST", Decimal("100.00"))
    h2 = compute_dedup_hash("ALICE SMITH", "1 MAIN ST", Decimal("200.00"))
    assert h1 != h2


def test_compute_dedup_hash_returns_none_for_all_blank():
    assert compute_dedup_hash(None, None, None) is None
    assert compute_dedup_hash("", "", None) is None
    assert compute_dedup_hash("  ", "  ", None) is None


# --- split_address_freeform -------------------------------------------------

def test_split_address_freeform_extracts_state_and_zip():
    parts = split_address_freeform("123 Main St, Boston, MA 02101")
    assert parts["state"] == "MA"
    assert parts["zip"] == "02101"
    assert parts["city"] == "Boston"
    assert parts["address_line1"] is not None
    assert "Main" in parts["address_line1"]
