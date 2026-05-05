"""Unit tests for the scoring engine. No DB, no YAML loading per case."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.models import EntityType, NormalizedRecord, Priority
from score.rules import DEFAULT_CONFIG_PATH, apply_rules, load_config


CONFIG: dict[str, Any] = {
    "amount_tiers": [
        {"min": 10000, "points": 25, "label": "tier_10k"},
        {"min": 1000, "points": 10, "label": "tier_1k"},
    ],
    "entity_type": {
        "estate": 18,
        "business": 8,
        "individual": 5,
        "unknown": 0,
    },
    "keywords": {"heir": 15, "deceased": 12},
    "age_years": [
        {"min": 10, "points": 10},
        {"min": 5, "points": 6},
    ],
    "has_address": 5,
    "priority_thresholds": {"high": 40, "medium": 20},
}


def _record(**overrides) -> NormalizedRecord:
    """Build a transient NormalizedRecord (not bound to a session)."""
    defaults = dict(
        owner_name_normalized="X",
        entity_type=EntityType.individual,
        claim_amount=None,
        record_age_years=None,
        keywords_found=[],
        address_line1=None,
        city=None,
        state=None,
        zip=None,
        property_type=None,
        source="test",
    )
    defaults.update(overrides)
    return NormalizedRecord(**defaults)


# --- amount_tier ------------------------------------------------------------

def test_amount_tier_picks_first_matching_tier():
    result = apply_rules(_record(claim_amount=Decimal("15000")), CONFIG)
    assert result.breakdown["amount_tier"]["matched"] == "tier_10k"
    assert result.breakdown["amount_tier"]["points"] == 25


def test_amount_tier_falls_through_to_lower_tier():
    result = apply_rules(_record(claim_amount=Decimal("2000")), CONFIG)
    assert result.breakdown["amount_tier"]["matched"] == "tier_1k"


def test_amount_tier_skipped_when_amount_is_none():
    result = apply_rules(_record(claim_amount=None), CONFIG)
    assert "amount_tier" not in result.breakdown


def test_amount_tier_no_match_below_smallest_tier():
    result = apply_rules(_record(claim_amount=Decimal("50")), CONFIG)
    assert "amount_tier" not in result.breakdown


# --- entity_type ------------------------------------------------------------

def test_entity_type_estate_scores_high():
    result = apply_rules(_record(entity_type=EntityType.estate), CONFIG)
    assert result.breakdown["entity_type"]["matched"] == "estate"
    assert result.breakdown["entity_type"]["points"] == 18


def test_entity_type_unknown_adds_nothing():
    result = apply_rules(_record(entity_type=EntityType.unknown), CONFIG)
    assert "entity_type" not in result.breakdown


# --- keywords ---------------------------------------------------------------

def test_keywords_match_case_insensitive():
    result = apply_rules(_record(keywords_found=["HEIR", "Other"]), CONFIG)
    assert result.breakdown["keywords"]["matched"] == ["heir"]
    assert result.breakdown["keywords"]["points"] == 15


def test_keywords_sum_when_multiple_match():
    result = apply_rules(_record(keywords_found=["heir", "deceased"]), CONFIG)
    assert set(result.breakdown["keywords"]["matched"]) == {"heir", "deceased"}
    assert result.breakdown["keywords"]["points"] == 27


def test_keywords_no_match_no_breakdown_entry():
    result = apply_rules(_record(keywords_found=["irrelevant"]), CONFIG)
    assert "keywords" not in result.breakdown


# --- age_years --------------------------------------------------------------

def test_age_uses_first_matching_tier():
    result = apply_rules(_record(record_age_years=12), CONFIG)
    assert result.breakdown["age_years"]["points"] == 10


def test_age_skipped_when_none():
    result = apply_rules(_record(record_age_years=None), CONFIG)
    assert "age_years" not in result.breakdown


# --- has_address ------------------------------------------------------------

def test_has_address_bonus_when_any_component_present():
    result = apply_rules(_record(city="Boston"), CONFIG)
    assert result.breakdown["has_address"]["points"] == 5


def test_no_address_bonus_when_all_blank():
    result = apply_rules(_record(), CONFIG)
    assert "has_address" not in result.breakdown


# --- priority + total -------------------------------------------------------

def test_priority_high_above_high_threshold():
    # 25 (tier_10k) + 18 (estate) + 5 (address) = 48 >= 40
    result = apply_rules(
        _record(
            claim_amount=Decimal("15000"),
            entity_type=EntityType.estate,
            city="Boston",
        ),
        CONFIG,
    )
    assert result.score == 48
    assert result.priority == Priority.high


def test_priority_medium_between_thresholds():
    # 10 (tier_1k) + 8 (business) + 5 (address) = 23 (>= 20, < 40)
    result = apply_rules(
        _record(
            claim_amount=Decimal("1500"),
            entity_type=EntityType.business,
            city="Boston",
        ),
        CONFIG,
    )
    assert result.score == 23
    assert result.priority == Priority.medium


def test_priority_low_below_medium_threshold():
    # individual 5 + tier_1k 10 = 15 (< 20)
    result = apply_rules(
        _record(claim_amount=Decimal("1500"), entity_type=EntityType.individual),
        CONFIG,
    )
    assert result.priority == Priority.low


def test_breakdown_total_matches_score():
    result = apply_rules(
        _record(claim_amount=Decimal("1500"), entity_type=EntityType.business),
        CONFIG,
    )
    assert result.breakdown["total"] == result.score


# --- default YAML loads -----------------------------------------------------

def test_default_config_yaml_loads_with_expected_sections():
    config = load_config(DEFAULT_CONFIG_PATH)
    assert "amount_tiers" in config
    assert "entity_type" in config
    assert "priority_thresholds" in config
    assert config["priority_thresholds"]["high"] > config["priority_thresholds"]["medium"]
