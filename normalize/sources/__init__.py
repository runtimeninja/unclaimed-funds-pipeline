"""Concrete normalizers, one per source.

Real-source normalizers live here. As they're added, register them in
`DEFAULT_NORMALIZERS` so the CLI picks them up automatically.

Per-test normalizers belong inside the test file that uses them, not here.
"""
from __future__ import annotations

from normalize.base import BaseNormalizer

# Populated as real sources are added.
DEFAULT_NORMALIZERS: dict[str, BaseNormalizer] = {}

__all__ = ["DEFAULT_NORMALIZERS"]
