"""Concrete normalizers, one per source.

Real-source normalizers live here. As they're added, register them in
`DEFAULT_NORMALIZERS` so the CLI picks them up automatically.

Per-test normalizers belong inside the test file that uses them, not here.
"""
from __future__ import annotations

from normalize.base import BaseNormalizer
from normalize.sources.sample_us import SOURCE as SAMPLE_US_SOURCE, SampleUSNormalizer

DEFAULT_NORMALIZERS: dict[str, BaseNormalizer] = {
    SAMPLE_US_SOURCE: SampleUSNormalizer(),
}

__all__ = ["DEFAULT_NORMALIZERS"]
