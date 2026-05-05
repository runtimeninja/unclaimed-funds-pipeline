"""Drive a `BaseIngester` to completion and write rows into `raw_records`.

Semantics:
  - Each run gets a fresh `file_batch_id` of the form
    '<source>:<UTC timestamp>:<short uuid>'.
  - Records are flushed to the DB in batches of `batch_size` (default 500)
    so memory stays bounded even for large sources.
  - All writes happen inside one session/transaction. If `iter_records`
    raises, the transaction rolls back — nothing from this run lands in
    the DB.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from db.models import RawRecord
from db.session import get_session
from ingest.base import BaseIngester


@dataclass(frozen=True)
class IngestResult:
    file_batch_id: str
    count: int


def run_ingest(ingester: BaseIngester, *, batch_size: int = 500) -> IngestResult:
    """Run `ingester` to completion. Returns the batch id and row count."""
    file_batch_id = _make_batch_id(ingester.source)
    logger.info(
        f"Starting ingest source='{ingester.source}' batch_id={file_batch_id}"
    )

    total = 0
    pending: list[RawRecord] = []

    with get_session() as session:
        for record in ingester.iter_records():
            pending.append(
                RawRecord(
                    source=ingester.source,
                    raw_data=record,
                    file_batch_id=file_batch_id,
                )
            )
            if len(pending) >= batch_size:
                session.add_all(pending)
                session.flush()
                total += len(pending)
                pending.clear()

        if pending:
            session.add_all(pending)
            session.flush()
            total += len(pending)

    logger.success(
        f"Ingested {total} record(s) source='{ingester.source}' "
        f"batch_id={file_batch_id}"
    )
    return IngestResult(file_batch_id=file_batch_id, count=total)


def _make_batch_id(source: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{source}:{ts}:{short}"
