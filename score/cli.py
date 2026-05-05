"""Manual entry point for running scoring.

Examples:
    python -m score.cli
    python -m score.cli --config path/to/custom_rules.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from score.runner import run_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="score",
        description="Score all normalized_records that don't yet have a scored_leads row.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a scoring rules YAML (defaults to score/config.yaml).",
    )
    args = parser.parse_args(argv)

    summary = run_score(config_path=args.config)
    logger.info(
        f"Done. processed={summary.processed} "
        f"high={summary.by_priority['high']} "
        f"medium={summary.by_priority['medium']} "
        f"low={summary.by_priority['low']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
