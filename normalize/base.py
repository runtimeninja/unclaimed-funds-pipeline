"""Base contract for source-specific normalizers.

A normalizer pulls fields out of one source's raw JSONB shape and returns a
common-shape `RawFields` dataclass. The shared parsers in `normalize.fields`
then turn those text fields into a typed `NormalizedRecord`.

Keep `extract()` thin: it should only do key lookups and very light cleanup.
Don't parse amounts, addresses, or detect entity types here — the runner will.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawFields:
    """Common-shape fields a normalizer pulls from one raw record.

    Everything is text-or-None on purpose; coercion happens in the runner.
    """

    owner_name: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    claim_amount_text: str | None = None
    property_type: str | None = None
    keywords_found: list[str] = field(default_factory=list)


class BaseNormalizer(ABC):
    """Map one source's raw_data dict into the common `RawFields` shape."""

    source: str

    @abstractmethod
    def extract(self, raw: dict[str, Any]) -> RawFields:
        """Pull fields out of `raw`. Return None for fields not present."""
