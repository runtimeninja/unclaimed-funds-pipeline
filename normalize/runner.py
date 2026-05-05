"""Drive normalizers across un-normalized raw_records.

Selection rule: any raw_record without a normalized child is in scope.
Per record:
  - look up normalizer by raw.source; if missing, skip with a counter bump
  - extract RawFields, apply shared parsers, build a NormalizedRecord
  - if dedup_hash matches an existing or in-flight record, skip as duplicate
  - else add to the session

All work runs in one transaction. If anything raises, the run rolls back —
nothing partial lands.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

from db.models import NormalizedRecord, RawRecord
from db.session import get_session
from normalize.base import BaseNormalizer, RawFields
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


@dataclass(frozen=True)
class NormalizeResult:
    processed: int
    skipped_no_normalizer: int
    skipped_duplicate: int
    total_seen: int


def run_normalize(
    normalizers: dict[str, BaseNormalizer],
    *,
    flush_every: int = 500,
) -> NormalizeResult:
    """Normalize all raw_records that don't yet have a normalized child."""
    processed = 0
    skipped_no_normalizer = 0
    skipped_duplicate = 0
    total_seen = 0
    seen_hashes_this_run: set[str] = set()

    stmt = (
        select(RawRecord)
        .outerjoin(
            NormalizedRecord, NormalizedRecord.raw_record_id == RawRecord.id
        )
        .where(NormalizedRecord.id.is_(None))
        .order_by(RawRecord.ingested_at)
    )

    with get_session() as session:
        for raw in session.scalars(stmt).yield_per(flush_every):
            total_seen += 1
            normalizer = normalizers.get(raw.source)
            if normalizer is None:
                skipped_no_normalizer += 1
                continue

            fields = normalizer.extract(raw.raw_data)
            normalized = _build_normalized(raw, fields)

            if normalized.dedup_hash:
                if normalized.dedup_hash in seen_hashes_this_run:
                    skipped_duplicate += 1
                    continue
                already = session.scalar(
                    select(NormalizedRecord.id).where(
                        NormalizedRecord.dedup_hash == normalized.dedup_hash
                    )
                )
                if already is not None:
                    skipped_duplicate += 1
                    continue
                seen_hashes_this_run.add(normalized.dedup_hash)

            session.add(normalized)
            processed += 1

            if processed % flush_every == 0:
                session.flush()

    logger.success(
        f"Normalize done: processed={processed} "
        f"skipped_duplicate={skipped_duplicate} "
        f"skipped_no_normalizer={skipped_no_normalizer} "
        f"total_seen={total_seen}"
    )
    return NormalizeResult(
        processed=processed,
        skipped_no_normalizer=skipped_no_normalizer,
        skipped_duplicate=skipped_duplicate,
        total_seen=total_seen,
    )


def _build_normalized(raw: RawRecord, fields: RawFields) -> NormalizedRecord:
    name = normalize_name(fields.owner_name)
    entity_type = detect_entity_type(name)

    line1 = clean_text(fields.address_line1)
    city = clean_text(fields.city)
    state = clean_state(fields.state)
    zip_code = clean_zip(fields.zip)

    # If the source gave us only a freeform line1, try to split it.
    if line1 and not (city and state and zip_code):
        parts = split_address_freeform(line1)
        if parts["state"] or parts["city"] or parts["zip"]:
            line1 = parts["address_line1"] or line1
            city = city or clean_text(parts["city"])
            state = state or clean_state(parts["state"])
            zip_code = zip_code or clean_zip(parts["zip"])

    amount = parse_claim_amount(fields.claim_amount_text)
    dedup = compute_dedup_hash(name, line1, amount)

    return NormalizedRecord(
        raw_record_id=raw.id,
        owner_name_normalized=name,
        entity_type=entity_type,
        address_line1=line1,
        city=city,
        state=state,
        zip=zip_code,
        claim_amount=amount,
        property_type=clean_text(fields.property_type),
        record_age_years=None,
        keywords_found=list(fields.keywords_found or []),
        source=raw.source,
        dedup_hash=dedup,
    )
