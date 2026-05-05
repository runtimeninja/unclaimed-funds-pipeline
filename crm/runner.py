"""Export un-exported scored_leads to Airtable.

Selection: ScoredLead rows where `exported_to_crm IS FALSE`. Records are
pushed in batches of `batch_size` (Airtable's API caps batches at 10),
highest-score first.

Per chunk:
  - build Airtable record dicts via crm.mapping.build_airtable_fields
  - call client.create_records(...)
  - on success: mark each record exported_to_crm=True and store the returned
    airtable_record_id + exported_at timestamp
  - on failure: log and continue with the next chunk; the failed records
    stay un-exported and will be picked up on the next run

Each successful chunk is its own DB flush so partial progress survives
mid-run failures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import islice
from typing import Iterable, Iterator, TypeVar

from loguru import logger
from sqlalchemy import select

from crm.airtable import AirtableClient, build_default_client
from crm.mapping import build_airtable_fields
from db.models import NormalizedRecord, ScoredLead
from db.session import get_session


T = TypeVar("T")


@dataclass(frozen=True)
class ExportResult:
    exported: int
    failed: int
    total_seen: int


def run_export(
    *,
    client: AirtableClient | None = None,
    batch_size: int = 10,
) -> ExportResult:
    """Push every un-exported scored lead to Airtable."""
    if client is None:
        client = build_default_client()

    exported = 0
    failed = 0

    stmt = (
        select(ScoredLead, NormalizedRecord)
        .join(NormalizedRecord, ScoredLead.normalized_record_id == NormalizedRecord.id)
        .where(ScoredLead.exported_to_crm.is_(False))
        .order_by(ScoredLead.score.desc())
    )

    with get_session() as session:
        rows = list(session.execute(stmt).all())
        total_seen = len(rows)

        for chunk in _chunked(rows, batch_size):
            payload = [build_airtable_fields(s, n) for s, n in chunk]
            try:
                created = client.create_records(payload)
            except Exception as exc:
                logger.error(
                    f"Airtable batch_create failed for {len(chunk)} record(s): "
                    f"{exc.__class__.__name__}: {exc}"
                )
                failed += len(chunk)
                continue

            now = datetime.now(timezone.utc)
            for (scored, _normalized), result in zip(chunk, created):
                scored.exported_to_crm = True
                scored.exported_at = now
                scored.airtable_record_id = result["id"]
            session.flush()
            exported += len(chunk)

    logger.success(
        f"Export done: exported={exported} failed={failed} "
        f"total_seen={total_seen}"
    )
    return ExportResult(exported=exported, failed=failed, total_seen=total_seen)


def _chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    iterator = iter(items)
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            return
        yield chunk
