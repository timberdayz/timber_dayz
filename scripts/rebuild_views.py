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
    python scripts/rebuild_views.py --all-plain-views   # 只重建全部普通视图（部署期用）
    python scripts/rebuild_views.py --target mart.inventory_state
    python scripts/rebuild_views.py --dry-run           # 只看会重建什么

⚠️ 重建期间会短暂持有排他锁 → 看板查询可能转圈、商品中心的保存会短暂等待。
   脚本**单进程串行**执行（不会并发），所以不会自己跟自己死锁。

``--all-plain-views`` 是部署期用的模式：数据刷新流程会跳过「已存在的普通视图」
（2026-10-26 排他锁事故的正解），所以视图**定义**的变更必须靠部署期这次
显式重建落地。清单由 refresh registry + 库里实际存在的视图算出，不写死。
物化视图**不在**其中 —— 它们由迁移建、由数据刷新原地 REFRESH，
部署期重建要全量重算（生产实测单个月粒度 MV 就超过 120s statement_timeout）。
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


async def _materialized_view_targets(db: Any) -> list[str]:
    """库里**全部**物化视图（不限 registry）—— 用来发现「被连带删掉」的。"""
    result = await db.execute(
        text(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'm'
            ORDER BY 1
            """
        )
    )
    return [row[0] for row in result.fetchall()]


async def _plain_view_targets(db: Any) -> list[str]:
    """库里已存在的**普通视图**（relkind='v'），且登记了 SQL 文件。

    为什么只收普通视图、不收物化视图
    ------------------------------
    物化视图的正文是**物化**出来的：重建 = 全量重算 + 写存储 + 建索引。
    生产实测单个月粒度 MV 就要 100 秒以上（38,607 行的原子层是 114.6 秒），
    超过生产默认 ``statement_timeout=120s`` ⇒ 部署期重建会直接超时
    （v7.13.0 首次发布就是这么失败的：迁移事务整体回滚，生产自动回滚）。

    物化视图的职责分工是清楚的：
    - **建**：由迁移负责（见 ``current_migrations/versions/``）；
    - **刷数据**：由数据刷新负责（``refresh_runner`` 原地 REFRESH）；
    - **改定义**：由本脚本或对应迁移负责。
    """
    result = await db.execute(
        text(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'v'
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


async def _heal_vanished_materialized_views(
    db: Any,
    known: set[str],
    failed: list[str],
    recreated: list[str],
    *,
    label: str,
) -> set[str]:
    """把「被普通视图的 ``DROP ... CASCADE`` 连带删掉」的物化视图建回来。

    为什么必须**立刻**做（而不是全部重建完再做）
    ----------------------------------------------
    重建普通视图 ``semantic.fact_analytics_atomic`` 时，它的资产文件开头的
    ``DROP VIEW ... CASCADE`` 会把下游物化视图
    ``semantic.fact_analytics_atomic_mv`` **连带删掉**（本地实跑 + 生产
    pg_depend 闭包都已确认）。

    而 ``mart.shop_day_kpi`` 的定义**要读那个物化视图** ⇒ 如果等到全部重建完
    才自愈，``mart.shop_day_kpi`` 这一步就会直接失败：
    ``relation "semantic.fact_analytics_atomic_mv" does not exist``。

    所以每重建一个目标就立刻检查一次「有没有物化视图被连带删掉」，
    有就当场按资产文件建回来（那些资产文件自带
    「存在则 REFRESH / 不存在则 CREATE」，重建代价很低），
    后面的目标就能看到它 —— 整个重建链不中断。

    建不回来就明确失败，不留半坏的库上线。
    """
    current = set(await _materialized_view_targets(db))
    vanished = sorted(known - current)
    if not vanished:
        return known
    print(f"   ⚠️ {label}连带删掉了 {len(vanished)} 个物化视图，正在按资产文件重建：")
    for target in vanished:
        if target not in SQL_TARGET_PATHS:
            failed.append(target)
            print(f"      ❌ {target} → 没有登记的 SQL 资产，无法重建")
            continue
        try:
            # 用 SAVEPOINT 包住：建失败只回滚这一件事，不牵连已经重建好的视图。
            async with db.begin_nested():
                await execute_sql_target(
                    db,
                    target,
                    pipeline_name="rebuild_views_recreate_materialized",
                    trigger_source="manual",
                    recreate_views=True,
                    resolve_dependencies=False,
                )
            recreated.append(target)
            known.add(target)
            print(f"      ♻️ {target}")
        except Exception as exc:  # noqa: BLE001
            failed.append(target)
            print(f"      ❌ {target} → {exc}")
    return known


async def rebuild(
    targets: list[str],
    dry_run: bool = False,
    all_plain_views: bool = False,
) -> int:
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
            wanted = []
        if all_plain_views:
            # 数据刷新流程现在会**跳过**已存在的普通视图（2026-10-26 排他锁事故的正解），
            # 所以「改了 sql/ 里的视图定义」必须由部署期这次显式重建落地。
            # 清单由 registry + 库里实际存在的视图算出来，不写死 —— 写死一定会漏。
            plain = await _plain_view_targets(db)
            wanted = list(dict.fromkeys(list(wanted) + list(plain)))
        if not wanted:
            print("没有需要重建的视图目标")
            return 0
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
        rebuilt: list[str] = []
        recreated: list[str] = []
        # 重建前的物化视图清单：用来发现「被普通视图的 DROP ... CASCADE 连带删掉」的。
        matviews_before = set(await _materialized_view_targets(db))
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
                rebuilt.append(target)
                print(f"   ✅ {target}")
            except Exception as exc:  # noqa: BLE001
                failed.append(target)
                print(f"   ❌ {target} → {exc}")
                if hasattr(db, "rollback"):
                    await db.rollback()
                    # 回滚把前面已经重建好的视图也一起撤销了 → 重新拍一次物化视图清单
                    matviews_before = set(await _materialized_view_targets(db))
                continue
            # 立刻自愈：这一步的 DROP ... CASCADE 可能把下游物化视图连带删掉了。
            # 必须**当场**建回来 —— 后面的目标（比如 mart.shop_day_kpi）要读它，
            # 等到全部重建完再自愈就来不及了。
            matviews_before = await _heal_vanished_materialized_views(
                db,
                matviews_before,
                failed,
                recreated,
                label=f"重建 {target} 时",
            )
        if hasattr(db, "commit"):
            await db.commit()

        print()
        print(
            f"重建完成：成功 {len(rebuilt)} 个，失败 {len(failed)} 个"
            + (f"，自愈重建物化视图 {len(recreated)} 个" if recreated else "")
        )
        # 机器可读：部署脚本用它复核「重建出来的视图确实存在」。
        print("REBUILT_TARGETS: " + " ".join(rebuilt))
        if recreated:
            print("RECREATED_MATERIALIZED_VIEWS: " + " ".join(recreated))
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="显式重建视图链（改了视图定义后跑）")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="只重建指定目标（可重复）；不给则重建全部",
    )
    parser.add_argument(
        "--all-plain-views",
        action="store_true",
        help=(
            "重建库里已存在的全部普通视图（物化视图除外：它们由迁移负责建、"
            "由数据刷新负责原地 REFRESH，部署期重建会超时）"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="只看会重建什么，不真跑")
    args = parser.parse_args()
    return asyncio.run(
        rebuild(args.target, dry_run=args.dry_run, all_plain_views=args.all_plain_views)
    )


if __name__ == "__main__":
    raise SystemExit(main())
