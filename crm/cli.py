"""Manual entry point for running the Airtable export.

Examples:
    python -m crm.cli
    python -m crm.cli --batch-size 10
"""
from __future__ import annotations

import argparse
import sys

from loguru import logger

from crm.runner import run_export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crm-export",
        description="Push un-exported scored_leads to Airtable.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Records per Airtable batch (Airtable's API caps this at 10).",
    )
    args = parser.parse_args(argv)

    summary = run_export(batch_size=args.batch_size)
    logger.info(
        f"Done. exported={summary.exported} failed={summary.failed} "
        f"total_seen={summary.total_seen}"
    )
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
