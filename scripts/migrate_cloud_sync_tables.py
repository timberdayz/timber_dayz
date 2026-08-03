#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Create cloud-sync tables required by a local source or cloud target database."""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from modules.core.db import (
    Base,
    CloudBClassSyncCheckpoint,
    CloudBClassSyncRun,
    CloudBClassSyncTask,
    CloudSyncReceiveLog,
    RefreshQueueTask,
)
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create cloud-sync runtime tables")
    parser.add_argument(
        "--target",
        action="store_true",
        help="Initialize only the cloud receiver tables using CLOUD_DATABASE_URL",
    )
    return parser.parse_args(argv)


def initialize_cloud_sync_target(database_url: str) -> None:
    cloud_engine = create_engine(database_url)
    try:
        with cloud_engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        Base.metadata.create_all(
            bind=cloud_engine,
            tables=[
                CloudSyncReceiveLog.__table__,
                RefreshQueueTask.__table__,
            ],
        )
    finally:
        cloud_engine.dispose()


def initialize_local_sync_state() -> None:
    from backend.models.database import engine

    Base.metadata.create_all(
        bind=engine,
        tables=[
            CloudBClassSyncCheckpoint.__table__,
            CloudBClassSyncRun.__table__,
            CloudBClassSyncTask.__table__,
        ],
    )
    print("cloud sync state tables ensured")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.target:
        database_url = os.getenv("CLOUD_DATABASE_URL")
        if not database_url:
            raise RuntimeError("CLOUD_DATABASE_URL is required for --target")
        initialize_cloud_sync_target(database_url)
        print("cloud sync target tables ensured")
        return
    initialize_local_sync_state()


if __name__ == "__main__":
    main()
