"""Manual entry point for running an ingestion.

Examples:
    python -m ingest.cli csv ./data/sample.csv --source ny_csv
"""
from __future__ import annotations

import argparse
import sys

from loguru import logger

from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest", description="Run a raw-layer ingestion."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    csv_p = sub.add_parser("csv", help="Ingest a local CSV file.")
    csv_p.add_argument("path", help="Path to the CSV file.")
    csv_p.add_argument(
        "--source", required=True, help="Stable source identifier (e.g. ny_csv)."
    )
    csv_p.add_argument("--encoding", default="utf-8")

    args = parser.parse_args(argv)

    if args.cmd == "csv":
        ingester = CSVFileIngester(
            path=args.path, source=args.source, encoding=args.encoding
        )
        result = run_ingest(ingester)
        logger.info(
            f"Done. batch_id={result.file_batch_id} count={result.count}"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
