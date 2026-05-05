"""Manual entry point for running normalization.

Examples:
    python -m normalize.cli
"""
from __future__ import annotations

import argparse
import sys

from loguru import logger

from normalize.runner import run_normalize
from normalize.sources import DEFAULT_NORMALIZERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="normalize",
        description="Normalize all raw_records that don't yet have a normalized child.",
    )
    parser.parse_args(argv)

    if not DEFAULT_NORMALIZERS:
        logger.warning(
            "No normalizers registered. Add one under normalize/sources/ "
            "and register it in normalize/sources/__init__.py before running."
        )
        return 0

    result = run_normalize(DEFAULT_NORMALIZERS)
    logger.info(
        f"Done. processed={result.processed} "
        f"skipped_duplicate={result.skipped_duplicate} "
        f"skipped_no_normalizer={result.skipped_no_normalizer}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
