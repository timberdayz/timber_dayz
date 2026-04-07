#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bootstrap or inspect PostgreSQL Dashboard assets on the current database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.models.database import AsyncSessionLocal
from backend.services.data_pipeline.dashboard_bootstrap import (
    DASHBOARD_BOOTSTRAP_TARGETS,
    DASHBOARD_REQUIRED_OBJECTS,
    bootstrap_dashboard_assets,
    inspect_dashboard_assets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap PostgreSQL Dashboard assets")
    parser.add_argument("--check", action="store_true", help="Only inspect assets and exit")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False))
        return

    print("=== PostgreSQL Dashboard Assets ===")
    print(f"ready: {report['ready']}")
    print(f"existing_schemas: {', '.join(report.get('existing_schemas', [])) or '(none)'}")
    if report.get("missing_schemas"):
        print(f"missing_schemas: {', '.join(report['missing_schemas'])}")
    if report.get("missing_objects"):
        print("missing_objects:")
        for name in report["missing_objects"]:
            print(f"- {name}")
    if report.get("run_id"):
        print(f"run_id: {report['run_id']}")


async def _async_main(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        if args.check:
            report = await inspect_dashboard_assets(session)
            _print_report(report, args.json)
            return 0 if report["ready"] else 1

        report = await bootstrap_dashboard_assets(session)
        await session.commit()
        _print_report(report, args.json)
        return 0 if report["ready"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
