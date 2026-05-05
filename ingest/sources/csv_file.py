"""Ingest a local CSV file as raw records.

Every row becomes one dict of {column_name: cell_value} stored verbatim in
`raw_records.raw_data`. Cells stay as strings — type coercion and cleanup
are the normalization stage's responsibility.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator

from ingest.base import BaseIngester


class CSVFileIngester(BaseIngester):
    """Stream rows from a local CSV file as raw dicts."""

    def __init__(
        self,
        path: str | Path,
        source: str,
        encoding: str = "utf-8",
    ) -> None:
        self.path = Path(path)
        self.source = source
        self.encoding = encoding

    def iter_records(self) -> Iterator[dict[str, Any]]:
        with self.path.open(newline="", encoding=self.encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield dict(row)
