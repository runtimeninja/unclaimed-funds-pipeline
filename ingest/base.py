"""Base contract for raw-layer ingesters.

An ingester yields one dict per source record. Everything else — batch IDs,
DB writes, transaction handling — is the runner's job (see `ingest.runner`).
Source-specific concerns (HTTP, CSV parsing, scraping, retries) belong in
the subclass implementations under `ingest.sources`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator


class BaseIngester(ABC):
    """Yield raw record dicts from a single source.

    Subclasses must:
      - set `source` to a stable, short identifier (e.g. 'ny_unclaimed_csv')
      - implement `iter_records()` to produce one dict per record

    Each yielded dict is stored verbatim as JSONB in `raw_records.raw_data`.
    Do not normalize here — that's a downstream stage.
    """

    source: str

    @abstractmethod
    def iter_records(self) -> Iterator[dict[str, Any]]:
        """Yield one dict per source record."""
