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
    DASHBOARD_ASSET_AVAILABLE_STATUSES,
    DASHBOARD_MODULE_TARGETS,
    DASHBOARD_REQUIRED_OBJECTS,
    converge_dashboard_assets,
    inspect_dashboard_assets,
    refresh_dashboard_materialization_assets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap PostgreSQL Dashboard assets"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only inspect assets and exit"
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    parser.add_argument(
        "--module",
        choices=[*DASHBOARD_MODULE_TARGETS.keys(), "all"],
        default="all",
        help="Dashboard module to inspect or bootstrap",
    )
    parser.add_argument(
        "--refresh-materializations",
        action="store_true",
        help=(
            "Only refresh the heavy dashboard materialization targets "
            "(skips rebuilding core definitions; does NOT guarantee convergence — "
            "use the default path for that)"
        ),
    )
    return parser


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        # `default=str` 是**最后一道兜底**：
        # 正常路径上 report 已被 `dashboard_bootstrap` 归一化成 JSON 原生类型
        # ⇒ 这里不该触发；一旦触发 = 上游还有漏网之鱼。
        # 但运维不能因为「打印报告」而崩 —— 拿不到结论比拿到一个降级结论更糟。
        print(json.dumps(report, ensure_ascii=False, default=str))
        return

    print("=== PostgreSQL Dashboard Assets ===")
    print(f"ready: {report['ready']}")
    if report.get("module"):
        print(f"module: {report['module']}")
    print(
        f"existing_schemas: {', '.join(report.get('existing_schemas', [])) or '(none)'}"
    )
    if report.get("missing_schemas"):
        print(f"missing_schemas: {', '.join(report['missing_schemas'])}")
    if report.get("missing_objects"):
        print("missing_objects:")
        for name in report["missing_objects"]:
            print(f"- {name}")
    modules = report.get("modules")
    if isinstance(modules, dict):
        print("modules:")
        for module_name, module_report in modules.items():
            print(
                f"- {module_name}: status={module_report.get('status')} "
                f"ready={module_report.get('ready')}"
            )
            core_missing = module_report.get("core_missing_objects") or []
            refresh_missing = module_report.get("refresh_missing_objects") or []
            if core_missing:
                print(f"  core_missing_objects: {', '.join(core_missing)}")
            if refresh_missing:
                print(f"  refresh_missing_objects: {', '.join(refresh_missing)}")
    if report.get("run_ids"):
        for module_name, run_id in report["run_ids"].items():
            print(f"run_id[{module_name}]: {run_id}")


async def _async_main(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        if args.check:
            report = await inspect_dashboard_assets(session)
            report["module"] = args.module
            _print_report(report, args.json)
            if args.module == "all":
                return 0 if report["ready"] else 1
            module_report = report["modules"].get(args.module, {})
            return (
                0
                if module_report.get("status") in DASHBOARD_ASSET_AVAILABLE_STATUSES
                else 1
            )

        if args.refresh_materializations:
            if not args.json:
                print(f"[refresh] module={args.module} phase=refresh-materializations")
            report = await refresh_dashboard_materialization_assets(
                session, module=args.module
            )
            await session.commit()
            report["module"] = args.module
            _print_report(report, args.json)
            if args.module == "all":
                return 0 if report["ready"] else 1
            module_report = report["modules"].get(args.module, {})
            return 0 if module_report.get("status") == "ready" else 1

        if not args.json:
            print(
                f"[bootstrap] module={args.module} phase=core+refresh "
                "(顺序链：核心重建 → 刷新物化 → 回写指纹 ⇒ 跑一次就收敛)"
            )
        report = await converge_dashboard_assets(session, module=args.module)
        await session.commit()
        report["module"] = args.module
        _print_report(report, args.json)
        if args.module == "all":
            return 0 if report["ready"] else 1
        module_report = report["modules"].get(args.module, {})
        return (
            0
            if module_report.get("status") in DASHBOARD_ASSET_AVAILABLE_STATUSES
            else 1
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
