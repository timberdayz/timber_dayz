#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""显式重建视图链 —— 改了视图定义之后跑这个。

为什么需要这个入口
------------------
数据刷新流程**不再重建普通视图**（见 ``refresh_runner.execute_sql_target``）：
普通视图的数据是查询时实时算的，数据刷新时重建它没有意义，
而 ``CREATE OR REPLACE VIEW`` 要拿 ACCESS EXCLUSIVE 排他锁 →
期间**所有**并发读写都被挡住，两个刷新进程还会沿视图链 ABBA 死锁。

代价是「改了 ``sql/`` 里的视图定义不会自动生效」—— 这个脚本就是补上这条通路。

用法::

    python scripts/rebuild_views.py                     # 重建全部视图
    python scripts/rebuild_views.py --target mart.inventory_state
    python scripts/rebuild_views.py --dry-run           # 只看会重建什么

⚠️ 重建期间会短暂持有排他锁 → 看板查询可能转圈、商品中心的保存会短暂等待。
   脚本**单进程串行**执行（不会并发），所以不会自己跟自己死锁。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.services.data_pipeline.refresh_registry import (  # noqa: E402
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)
from backend.services.data_pipeline.refresh_runner import (  # noqa: E402
    execute_sql_target,
)


async def _view_targets(db: Any) -> list[str]:
    """库里已存在的视图（普通视图 + 物化视图），且登记了 SQL 文件。"""
    result = await db.execute(
        text(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('v', 'm')
            ORDER BY 1
            """
        )
    )
    return [row[0] for row in result.fetchall() if row[0] in SQL_TARGET_PATHS]


async def _ordered_view_targets(db: Any, wanted: list[str]) -> list[str]:
    """按依赖顺序排好，只保留视图（不把上游的表带进来执行）。"""
    ordered = topologically_sort_targets(wanted)
    view_set = set(wanted)
    return [target for target in ordered if target in view_set]


async def rebuild(targets: list[str], dry_run: bool = False) -> int:
    async with AsyncSessionLocal() as db:
        available = await _view_targets(db)
        if not available:
            print("库里没有登记的视图目标，无需重建")
            return 0
        if targets:
            wanted = [t for t in targets if t in available]
            missing = [t for t in targets if t not in available]
            if missing:
                print(f"⚠️ 以下目标不是已登记的视图，跳过：{missing}")
        else:
            wanted = available
        ordered = await _ordered_view_targets(db, wanted)

        print(f"准备重建 {len(ordered)} 个视图（按依赖顺序，串行执行）：")
        for target in ordered:
            print(f"   - {target}")
        if dry_run:
            return 0
        if not ordered:
            return 0

        print()
        print("开始重建（期间看板查询可能短暂等待）…")
        failed: list[str] = []
        for target in ordered:
            try:
                await execute_sql_target(
                    db,
                    target,
                    pipeline_name="rebuild_views",
                    trigger_source="manual",
                    recreate_views=True,
                    resolve_dependencies=False,
                )
                print(f"   ✅ {target}")
            except Exception as exc:  # noqa: BLE001
                failed.append(target)
                print(f"   ❌ {target} → {exc}")
                if hasattr(db, "rollback"):
                    await db.rollback()
        if hasattr(db, "commit"):
            await db.commit()
        print()
        print(f"重建完成：成功 {len(ordered) - len(failed)} 个，失败 {len(failed)} 个")
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="显式重建视图链（改了视图定义后跑）")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="只重建指定目标（可重复）；不给则重建全部",
    )
    parser.add_argument("--dry-run", action="store_true", help="只看会重建什么，不真跑")
    args = parser.parse_args()
    return asyncio.run(rebuild(args.target, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
