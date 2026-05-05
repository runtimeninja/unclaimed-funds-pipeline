"""Pure scoring engine. No DB, no I/O at the call site.

`apply_rules(record, config)` returns a `ScoreResult` (score, priority,
breakdown). The runner is responsible for loading the config and writing
the result back to `scored_leads`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from db.models import NormalizedRecord, Priority


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


@dataclass(frozen=True)
class ScoreResult:
    score: int
    priority: Priority
    breakdown: dict[str, Any]


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Load and lightly validate the scoring rules YAML."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Scoring config at {config_path} must be a mapping.")
    return config


def apply_rules(record: NormalizedRecord, config: dict[str, Any]) -> ScoreResult:
    """Compute (score, priority, breakdown) for one normalized record."""
    score = 0
    breakdown: dict[str, Any] = {}

    score += _apply_amount_tier(record, config, breakdown)
    score += _apply_entity_type(record, config, breakdown)
    score += _apply_keywords(record, config, breakdown)
    score += _apply_age(record, config, breakdown)
    score += _apply_has_address(record, config, breakdown)

    breakdown["total"] = score
    priority = _resolve_priority(score, config)
    return ScoreResult(score=score, priority=priority, breakdown=breakdown)


def _apply_amount_tier(
    record: NormalizedRecord, config: dict[str, Any], breakdown: dict[str, Any]
) -> int:
    if record.claim_amount is None:
        return 0
    for tier in config.get("amount_tiers", []) or []:
        if record.claim_amount >= tier["min"]:
            breakdown["amount_tier"] = {
                "matched": tier["label"],
                "points": tier["points"],
            }
            return int(tier["points"])
    return 0


def _apply_entity_type(
    record: NormalizedRecord, config: dict[str, Any], breakdown: dict[str, Any]
) -> int:
    entity_cfg = config.get("entity_type", {}) or {}
    points = int(entity_cfg.get(record.entity_type.value, 0))
    if points:
        breakdown["entity_type"] = {
            "matched": record.entity_type.value,
            "points": points,
        }
    return points


def _apply_keywords(
    record: NormalizedRecord, config: dict[str, Any], breakdown: dict[str, Any]
) -> int:
    raw_cfg = config.get("keywords", {}) or {}
    keyword_cfg = {str(k).lower(): int(v) for k, v in raw_cfg.items()}
    matched: list[str] = []
    points = 0
    for kw in record.keywords_found or []:
        key = str(kw).lower()
        if key in keyword_cfg:
            points += keyword_cfg[key]
            if key not in matched:
                matched.append(key)
    if matched:
        breakdown["keywords"] = {"matched": matched, "points": points}
    return points


def _apply_age(
    record: NormalizedRecord, config: dict[str, Any], breakdown: dict[str, Any]
) -> int:
    if record.record_age_years is None:
        return 0
    for tier in config.get("age_years", []) or []:
        if record.record_age_years >= tier["min"]:
            breakdown["age_years"] = {
                "matched_min": tier["min"],
                "points": tier["points"],
            }
            return int(tier["points"])
    return 0


def _apply_has_address(
    record: NormalizedRecord, config: dict[str, Any], breakdown: dict[str, Any]
) -> int:
    points = int(config.get("has_address", 0) or 0)
    if not points:
        return 0
    if any([record.address_line1, record.city, record.state, record.zip]):
        breakdown["has_address"] = {"points": points}
        return points
    return 0


def _resolve_priority(score: int, config: dict[str, Any]) -> Priority:
    thresholds = config.get("priority_thresholds", {}) or {}
    high = thresholds.get("high")
    medium = thresholds.get("medium")
    if high is not None and score >= high:
        return Priority.high
    if medium is not None and score >= medium:
        return Priority.medium
    return Priority.low
