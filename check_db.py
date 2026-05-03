"""Quick diagnostic: verify the app can reach PostgreSQL via DATABASE_URL.

Run with the venv active:  python check_db.py
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def main() -> int:
    load_dotenv(override=True)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL is not set. Did you copy .env.example to .env?")
        return 1

    safe_target = database_url.rsplit("@", 1)[-1]
    logger.info(f"Connecting to {safe_target} ...")

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar_one()
            current_db = conn.execute(text("SELECT current_database()")).scalar_one()
            current_user = conn.execute(text("SELECT current_user")).scalar_one()
    except SQLAlchemyError as exc:
        logger.error(f"Connection failed: {exc.__class__.__name__}: {exc}")
        return 2

    logger.success(f"Connected as user='{current_user}' to database='{current_db}'")
    logger.info(f"Server: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
