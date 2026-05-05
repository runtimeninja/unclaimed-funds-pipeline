"""Airtable adapter — a thin wrapper around pyairtable.

Anything matching the `AirtableClient` Protocol can be plugged into
`run_export`. Production wires up `RealAirtableClient`; tests inject a fake
so we never hit the real API in CI.
"""
from __future__ import annotations

import os
from typing import Any, Protocol


class AirtableClient(Protocol):
    """Minimal client surface used by the export runner."""

    def create_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create records in Airtable. Returns list of {'id': ..., 'fields': ...}."""
        ...


class RealAirtableClient:
    """Adapter over pyairtable's Table.batch_create with typecast=True.

    `typecast=True` lets Airtable accept loose values (string for a number
    field, unknown single-select option, etc.) and coerce/auto-create on
    its side.
    """

    def __init__(self, *, token: str, base_id: str, table_name: str) -> None:
        from pyairtable import Api  # lazy import: only the prod path needs it

        self._table = Api(token).table(base_id, table_name)

    def create_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return self._table.batch_create(records, typecast=True)


def build_default_client() -> AirtableClient:
    """Build a real client from .env. Raises if credentials are missing."""
    token = os.getenv("AIRTABLE_API_TOKEN")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_name = os.getenv("AIRTABLE_TABLE_NAME", "Leads")

    if not token or not base_id:
        raise RuntimeError(
            "AIRTABLE_API_TOKEN and AIRTABLE_BASE_ID must be set in .env. "
            "Generate a token at https://airtable.com/create/tokens, then "
            "grab the base id from your base's API docs."
        )

    return RealAirtableClient(
        token=token, base_id=base_id, table_name=table_name
    )
