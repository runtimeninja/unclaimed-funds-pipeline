"""Normalizer for the bundled sample US unclaimed-property dataset.

Source identifier: ``sample_us_unclaimed``. The data lives at
``data/sample_us_unclaimed.csv`` and is ingested via ``CSVFileIngester``;
this module only handles the raw -> RawFields mapping. The CSV's column
shape mirrors typical state holder reports (NAUPA-influenced):

    property_id, owner_name, owner_address, owner_city, owner_state,
    owner_zip, claim_amount, property_type_code, property_type_description,
    holder_name, reported_year

Real-state files we eventually plug in will get their own modules under
``normalize/sources/`` and follow the same pattern.

Two source-specific quirks the runner can't handle generically:
  * Some ``claim_amount`` cells are textual range descriptions rather
    than clean numbers (e.g., ``"AMOUNT INDICATED IS AT LEAST $100.00"``,
    ``"BETWEEN $50.00 AND $99.99"``). We extract a conservative numeric
    lower bound so scoring still has a tier to bite on; the original
    text is preserved in the raw record.
  * The downstream scorer reads keyword bonuses from a fixed list
    (``score/config.yaml``). We surface name-level signals here as
    ``keywords_found`` so estates / trusts pick up that extra bonus.
"""
from __future__ import annotations

import re
from typing import Any

from normalize.base import BaseNormalizer, RawFields


SOURCE = "sample_us_unclaimed"


# Lowercase markers we look for in the owner name. The scoring config keys
# off these exact strings (`score/config.yaml: keywords:`).
_NAME_KEYWORDS = ("estate", "trust", "heir", "deceased", "beneficiary")


# Range-description patterns. We deliberately match lower-bound only: leads
# from a range-only listing are inherently lower-confidence, and overshooting
# the value with the upper bound would inflate the priority tier.
_AT_LEAST_RE = re.compile(
    r"\bAT\s+LEAST\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_BETWEEN_RE = re.compile(
    r"BETWEEN\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


def coerce_amount_text(text: str | None) -> str | None:
    """Return a string the shared parser can interpret as a Decimal.

    Plain numeric strings pass through unchanged. Range descriptions are
    reduced to their lower bound. Empty / unrecognized input returns None.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None

    for pattern in (_AT_LEAST_RE, _BETWEEN_RE):
        m = pattern.search(stripped)
        if m:
            return m.group(1)
    return stripped


def find_name_keywords(owner_name: str | None) -> list[str]:
    if not owner_name:
        return []
    haystack = owner_name.lower()
    return [kw for kw in _NAME_KEYWORDS if kw in haystack]


class SampleUSNormalizer(BaseNormalizer):
    source = SOURCE

    def extract(self, raw: dict[str, Any]) -> RawFields:
        return RawFields(
            owner_name=raw.get("owner_name"),
            address_line1=raw.get("owner_address"),
            city=raw.get("owner_city"),
            state=raw.get("owner_state"),
            zip=raw.get("owner_zip"),
            claim_amount_text=coerce_amount_text(raw.get("claim_amount")),
            property_type=raw.get("property_type_description"),
            keywords_found=find_name_keywords(raw.get("owner_name")),
        )
