#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CLI entry point for manual B-class local-to-cloud sync."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local B-class tables to cloud")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--table", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def build_service_from_env(args: argparse.Namespace):
    from backend.services.cloud_b_class_auto_sync_factory import (
        build_cloud_sync_service_from_env,
    )

    return build_cloud_sync_service_from_env(dry_run=args.dry_run)


def main(argv: list[str] | None = None, service_factory=None) -> int:
    args = parse_args(argv)
    service = service_factory(args) if service_factory else build_service_from_env(args)

    try:
        if args.table:
            result = asyncio.run(service.sync_table(args.table, batch_size=args.batch_size))
            failed_tables = 0 if result.get("status") == "completed" else 1
        else:
            result = asyncio.run(service.sync_all_tables(batch_size=args.batch_size))
            failed_tables = int(result.get("failed_tables", 0))
        return 0 if failed_tables == 0 else 2
    finally:
        if hasattr(service, "close"):
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
