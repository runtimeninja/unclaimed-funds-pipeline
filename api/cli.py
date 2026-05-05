"""Manual entry point for running the API.

Examples:
    python -m api.cli                    # 127.0.0.1:8000, no reload
    python -m api.cli --reload           # hot reload on file changes
    python -m api.cli --port 9000

Reads `API_HOST` and `API_PORT` from .env if not overridden on the CLI.
"""
from __future__ import annotations

import argparse
import os
import sys

import uvicorn
from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(prog="api", description="Run the UFIP API.")
    parser.add_argument("--host", default=os.getenv("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
