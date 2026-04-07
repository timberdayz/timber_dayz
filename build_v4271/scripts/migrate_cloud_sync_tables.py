#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Create local cloud-sync state tables if they do not exist."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from modules.core.db import (
    Base,
    CloudBClassSyncCheckpoint,
    CloudBClassSyncRun,
    CloudBClassSyncTask,
)
from backend.models.database import engine


def main() -> None:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            CloudBClassSyncCheckpoint.__table__,
            CloudBClassSyncRun.__table__,
            CloudBClassSyncTask.__table__,
        ],
    )
    print("cloud sync state tables ensured")


if __name__ == "__main__":
    main()
