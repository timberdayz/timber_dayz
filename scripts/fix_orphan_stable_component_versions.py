"""清理指向已归档或缺失文件的 stable 组件版本记录。

依据：docs/guides/ACTIVE_COLLECTION_COMPONENTS.md:75
      —— 组件文件移入 archive/ 前，必须确认没有 stable 记录指向它。

默认 dry-run，只打印将要做的变更；加 --apply 才写库。
幂等：重复执行不产生额外副作用。

用法：
    python scripts/fix_orphan_stable_component_versions.py
    python scripts/fix_orphan_stable_component_versions.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from backend.models.database import AsyncSessionLocal, async_engine
from backend.services.active_collection_components import is_missing_component_file
from modules.core.db.schema import ComponentVersion


def find_orphaned_stable_records(rows: List[Any]) -> List[Any]:
    """筛出 is_stable=True 且 file_path 已失效的记录。"""
    return [
        row
        for row in rows
        if bool(getattr(row, "is_stable", False))
        and is_missing_component_file(getattr(row, "file_path", "") or "")
    ]


async def _collect_rows() -> List[Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ComponentVersion).where(ComponentVersion.is_stable.is_(True))
        )
        return list(result.scalars().all())


async def _apply(rows: List[Any]) -> int:
    """按主键重新查出来再改。

    ⚠️ 不能直接改 `_collect_rows()` 返回的实例：那个 session 已关闭，
    ORM 实例是 detached 的，对 detached 实例改字段再 `commit()` **不产生 UPDATE**——
    脚本会打印「已处理 N 条」而库里没变（静默 no-op）。
    """
    async with AsyncSessionLocal() as session:
        changed = 0
        for row in rows:
            target = await session.get(ComponentVersion, row.id)
            if target is None:
                continue
            target.is_stable = False
            changed += 1
        await session.commit()
        return changed


async def _run(apply: bool) -> int:
    """在**同一个**事件循环里完成「查 → 判 → 写」。

    ⚠️ 不能拆成两次 `asyncio.run()`：每次 `asyncio.run` 都会新建并关闭一个
    事件循环，连接池里已建立的 asyncpg 连接仍绑定在**上一个已关闭的循环**上，
    第二次取连接就会抛 `RuntimeError: Event loop is closed`（Windows
    ProactorEventLoop 上还会连带刷一串 asyncpg `_cancel` 未 await 的告警）。

    同理，退出前必须 `dispose()`：连接要在事件循环还活着的时候归还，
    否则归还动作会被派发到已关闭的循环上。
    """
    try:
        rows = await _collect_rows()
        orphans = find_orphaned_stable_records(rows)

        if not orphans:
            print("未发现指向缺失/已归档文件的 stable 记录，无需处理。")
            return 0

        for row in orphans:
            print(
                f"[dry-run] component_name={row.component_name} version={row.version} "
                f"file_path={row.file_path} -> is_stable=False"
            )

        if not apply:
            print(f"共 {len(orphans)} 条待处理记录。加 --apply 执行写库。")
            return 0

        changed = await _apply(orphans)
        print(f"已处理 {changed} 条记录。")
        return changed
    finally:
        await async_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="实际写库（默认只 dry-run）"
    )
    args = parser.parse_args()

    asyncio.run(_run(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
