"""重建库存状态层（`mart.inventory_state`）。

为什么需要这个脚本
------------------
「距上次进货天数」的唯一来源是状态层 ``mart.inventory_state``，
而它是**表**不是视图 —— SQL 资产重建只会 ``CREATE TABLE IF NOT EXISTS``，**灌不进数据**。

状态层唯一的写入方是 ``InventoryStateRefreshService``（upsert），
而它的生产调用方只有刷新队列消费者一个，且要求「事件带 ``data_domain=inventory``」。

⇒ 结果：部署脚本只重建了**库龄层**（``rebuild_inventory_age_from_snapshots.py``），
**状态层从来没被重建过** → 生产上 ``mart.inventory_state`` 是空表
→ 滞销榜恒 0 行（``age_days = COALESCE(days_since_restock, 0) = 0``，被 ``>= 30`` 全过滤掉）。

本脚本是库龄层脚本的**对称件**：部署时把状态层也重建一遍，
保证「发版后滞销榜立刻有数」。详见
``docs/architecture/SYNC_MODULE_REFACTOR_PLAN.md`` §3.9.11。

用法::

    python scripts/rebuild_inventory_state_from_snapshots.py --full-rebuild
    python scripts/rebuild_inventory_state_from_snapshots.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import AsyncSessionLocal
from backend.services.data_pipeline.inventory_state_refresh_service import (
    InventoryStateRefreshService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the persisted inventory state layer from inventory snapshots."
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Ignore the state-layer watermark and replay every snapshot row.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the refresh targets in dependency order.",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    service = InventoryStateRefreshService(db=None)
    targets = service.build_refresh_targets()

    if args.dry_run:
        print("inventory_state_refresh_targets")
        for target in targets:
            print(target)
        return 0

    async with AsyncSessionLocal() as session:
        service = InventoryStateRefreshService(db=session)
        result = await service.refresh(force_full=args.full_rebuild)
        await session.commit()
        print(f"inventory_state_refresh_result={result}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
