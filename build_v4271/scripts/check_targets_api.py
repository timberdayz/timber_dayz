#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标管理接口快速诊断脚本

在出现「查询失败」/ 500 时，于**与后端相同环境**下运行此脚本，
可看到后端返回的详细错误信息，便于排查表缺失、迁移未执行等问题。

用法（任选其一）：
  python scripts/check_targets_api.py
  或在项目根目录：python -m scripts.check_targets_api

依赖：当前环境需能连上后端使用的数据库（与后端 .env 中 DATABASE_URL 一致）。
"""

import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def main():
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.models.database import get_async_database_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from backend.utils.config import get_settings
    from modules.core.db import SalesTarget

    settings = get_settings()
    url = get_async_database_url(settings.DATABASE_URL)
    engine = create_async_engine(url, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    print("[1/3] 连接数据库...")
    async with session_factory() as db:
        try:
            # 与 list_targets 相同的 count 查询
            count_stmt = select(func.count(SalesTarget.id)).select_from(SalesTarget)
            r = await db.execute(count_stmt)
            total = r.scalar() or 0
            print(f"[2/3] sales_targets 表存在，当前条数: {total}")

            stmt = select(SalesTarget).order_by(SalesTarget.created_at.desc()).limit(5)
            r = await db.execute(stmt)
            rows = r.scalars().all()
            print(f"[3/3] 最近 {len(rows)} 条目标可读，list_targets 逻辑正常。")
            return 0
        except Exception as e:
            print(f"[FAIL] 错误类型: {type(e).__name__}")
            print(f"[FAIL] 错误信息: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
