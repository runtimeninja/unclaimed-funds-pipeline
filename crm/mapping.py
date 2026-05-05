"""Build Airtable record dicts from (ScoredLead, NormalizedRecord) pairs.

Field names match the Airtable column names expected on the configured
table. This module is the only place that knows about Airtable column
naming — change it here when the Airtable schema changes.
"""
from __future__ import annotations

import json
from typing import Any

from db.models import NormalizedRecord, ScoredLead


def build_airtable_fields(
    scored: ScoredLead, normalized: NormalizedRecord
) -> dict[str, Any]:
    return {
        "Name": normalized.owner_name_normalized,
        "Entity Type": normalized.entity_type.value,
        "Address Line 1": normalized.address_line1,
        "City": normalized.city,
        "State": normalized.state,
        "Zip": normalized.zip,
        "Claim Amount": (
            float(normalized.claim_amount)
            if normalized.claim_amount is not None
            else None
        ),
        "Source": normalized.source,
        "Priority": scored.priority.value,
        "Score": scored.score,
        # default=str so Decimal/datetime in the breakdown serialize cleanly.
        "Score Breakdown": json.dumps(scored.score_breakdown, default=str),
    }
