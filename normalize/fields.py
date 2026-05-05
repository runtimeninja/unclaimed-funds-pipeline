"""Shared field parsers used by the normalizer runner.

These functions are deliberately tolerant: bad/blank input returns None rather
than raising. Type coercion (Decimal, EntityType) happens here so source
modules stay tiny.
"""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation

import usaddress

from db.models import EntityType


# Tokens are matched on a space-padded uppercase name, so each marker is
# bounded by spaces on both sides. Keep this list conservative — false
# positives misclassify individuals as businesses.
_BUSINESS_MARKERS = (
    " LLC ",
    " L.L.C. ",
    " INC ",
    " INC. ",
    " CORP ",
    " CORP. ",
    " CO. ",
    " LP ",
    " L.P. ",
    " LLP ",
    " L.L.P. ",
    " PARTNERS ",
    " FUND ",
    " ASSOCIATES ",
    " ASSOC ",
    " COMPANY ",
    " HOLDINGS ",
    " GROUP ",
    " ENTERPRISES ",
    " SOLUTIONS ",
    " SERVICES ",
)
_TRUST_MARKER = " TRUST "
_ESTATE_PREFIX = "ESTATE OF "

_STATE_TWO_LETTER_RE = re.compile(r"^[A-Z]{2}$")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str | None) -> str | None:
    """Uppercase, collapse whitespace, strip trailing punctuation."""
    if not name:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", name.strip()).upper().rstrip(",.")
    return cleaned or None


def detect_entity_type(normalized_name: str | None) -> EntityType:
    """Heuristic classification based on tokens in the normalized name."""
    if not normalized_name:
        return EntityType.unknown
    if normalized_name.startswith(_ESTATE_PREFIX):
        return EntityType.estate
    padded = f" {normalized_name} "
    if any(marker in padded for marker in _BUSINESS_MARKERS):
        return EntityType.business
    if _TRUST_MARKER in padded:
        # Trusts behave like estates for outreach. Coarse for MVP.
        return EntityType.estate
    return EntityType.individual


def parse_claim_amount(text: str | None) -> Decimal | None:
    """Parse '$1,234.56' / '1234.56' / '' into Decimal or None."""
    if not text:
        return None
    cleaned = text.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", value.strip())
    return cleaned or None


def clean_state(state: str | None) -> str | None:
    """Uppercase. Returns 2-letter code untouched; longer values truncated to 8."""
    if not state:
        return None
    cleaned = state.strip().upper()
    if not cleaned:
        return None
    if _STATE_TWO_LETTER_RE.match(cleaned):
        return cleaned
    return cleaned[:8]


def clean_zip(zip_code: str | None) -> str | None:
    if not zip_code:
        return None
    return zip_code.strip() or None


_USADDRESS_LINE1_KEYS = (
    "AddressNumber",
    "AddressNumberPrefix",
    "AddressNumberSuffix",
    "StreetNamePreDirectional",
    "StreetNamePreModifier",
    "StreetNamePreType",
    "StreetName",
    "StreetNamePostType",
    "StreetNamePostDirectional",
    "StreetNamePostModifier",
    "OccupancyType",
    "OccupancyIdentifier",
)


def split_address_freeform(text: str) -> dict[str, str | None]:
    """Best-effort split of a freeform US address into parts via usaddress.

    On parse failure, returns the whole string as `address_line1` and the
    other fields as None. Always returns the four expected keys.
    """
    try:
        tagged, _ = usaddress.tag(text)
    except usaddress.RepeatedLabelError:
        return {
            "address_line1": text.strip() or None,
            "city": None,
            "state": None,
            "zip": None,
        }

    line1_parts = [tagged[k] for k in _USADDRESS_LINE1_KEYS if k in tagged]
    line1 = " ".join(line1_parts).strip() or None
    return {
        "address_line1": line1,
        "city": tagged.get("PlaceName"),
        "state": tagged.get("StateName"),
        "zip": tagged.get("ZipCode"),
    }


def compute_dedup_hash(
    name: str | None,
    address_line1: str | None,
    claim_amount: Decimal | None,
) -> str | None:
    """SHA-256 over the three canonicalised dedup components.

    Returns None when all three are blank — there's nothing to dedup on.
    """
    name_part = (name or "").strip().upper()
    addr_part = (address_line1 or "").strip().upper()
    amount_part = f"{claim_amount:.2f}" if claim_amount is not None else ""

    if not (name_part or addr_part or amount_part):
        return None

    payload = f"{name_part}|{addr_part}|{amount_part}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
