#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对候选集**物化副本**是不是还在「从正本取数」(只读)。

为什么要有这个脚本
------------------
候选集的口径**只有正本一处**定义::

    semantic.shop_identity_resolution_candidates        (正本, 普通视图)

而它的物化加速副本::

    semantic.shop_identity_resolution_candidates_v2_mv  (副本)

**曾经**手抄了一份正本的计算逻辑。两边靠人工保持一致 ——
一旦漂移, 漂移是**静默**的: 不报错、不告警, 看板只会表现为「某个店没人了」。

2026-11-11 生产实测(只读探测)::

    副本定义里仍然出现 core.shop_accounts / regexp_replace / active_shop_accounts
    ⇒ 它在**自算**, 没有读正本
    副本 72 行、正本 72 行、双向差集 0/0 ⇒ *当前* 内容一致, 无功能影响
    但副本的定义比正本**少一条**口径(采集方代号不进候选池) ⇒ 随时可能分叉

⇒ 这个脚本把「副本是否还在自算」「副本与正本是否一致」变成**一条命令**。

口径 SSOT
---------
⚠️ **不另写一份判定逻辑** —— 脚本直接调用巡检的
:func:`collect_identity_candidates_copy`(同一个函数、同一个判据),
所以「脚本看到的」= 「巡检会判的」, **不会分叉**。

安全边界
--------
1. **只读** —— 全程只有 ``SELECT``;
2. 连接串**只从环境变量读** (``CLOUD_DATABASE_URL``), 源码里**零字面量**;
3. 解析用 ``sqlalchemy.engine.make_url()``;
4. 输出**脱敏**(只留 driver/host/port/库名, 绝不含口令)。

用法
----
看云端(默认, 走本机隧道)::

    python scripts/verify_identity_candidates_copy.py

看本地::

    python scripts/verify_identity_candidates_copy.py --target local

退出码
------
``0`` = 副本健康 / ``1`` = 副本有问题(自算 / 分叉 / 缺失) / ``2`` = 参数或连接有问题。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from backend.utils.project_env import load_project_env  # noqa: E402

# ⚠️ **必须先加载 .env 再 import backend 模块** ——
# ``backend.models.database`` 在 import 时就会按 ``DATABASE_URL`` 建引擎,
# 环境变量还没加载 ⇒ 引擎会指向错误的目标(或者建不出来)。
load_project_env(_PROJECT_ROOT, profile="collection")

from backend.models.database import get_async_database_url  # noqa: E402
from backend.services.data_pipeline.cloud_sync_integrity_service import (  # noqa: E402
    IDENTITY_CANDIDATES_MV,
    IDENTITY_CANDIDATES_VIEW,
    collect_identity_candidates_copy,
)
from backend.tasks.cloud_sync_integrity_tasks import (  # noqa: E402
    resolve_cloud_database_url_from_env,
)


def safe_print(message: str) -> None:
    """打印(Windows 终端可能不是 UTF-8 ⇒ 兜住编码错误)。"""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("gbk", errors="ignore").decode("gbk"), flush=True)


def _masked_target(raw_url: str) -> str:
    """把连接串压成**脱敏**目标串(只留 driver/host/端口/库名, 绝不含口令)。"""
    parsed = make_url(raw_url)
    driver = parsed.drivername.split("+", 1)[0]
    return "%s://%s:%s/%s" % (
        driver,
        parsed.host or "",
        parsed.port or 5432,
        parsed.database or "",
    )


def _resolve_target(target: str) -> str:
    """按目标取连接串(只从环境变量读)。"""
    if target == "cloud":
        resolution = resolve_cloud_database_url_from_env()
        url = resolution.url
        if not url:
            raise SystemExit("CLOUD_DATABASE_URL 未配置(云端隧道是否在线?)")
        return url
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL 未配置")
    return url


async def _collect(url: str) -> object:
    engine = create_async_engine(get_async_database_url(url))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        return await collect_identity_candidates_copy(db)
    finally:
        await db.close()
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="核对候选集物化副本是否还在「从正本取数」(只读, 复用巡检判据)"
    )
    parser.add_argument(
        "--target",
        choices=["cloud", "local"],
        default="cloud",
        help="看云端(默认)还是本地",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    url = _resolve_target(args.target)
    row = asyncio.run(_collect(url))

    safe_print("目标     = %s" % _masked_target(url))
    safe_print("正本     = %s" % IDENTITY_CANDIDATES_VIEW)
    safe_print("副本     = %s" % IDENTITY_CANDIDATES_MV)
    safe_print("")

    if row is None:
        safe_print("【结论】这个环境没有候选池 ⇒ 不适用(不算问题)。")
        return 0

    safe_print("状态     = %s" % row.status)
    safe_print("从正本取数 = %s" % ("是" if row.reads_source else "否"))
    safe_print("副本行数 = %s" % row.copy_rows)
    safe_print("正本行数 = %s" % row.source_rows)
    safe_print("仅正本有 = %s" % row.view_only_rows)
    safe_print("仅副本有 = %s" % row.copy_only_rows)
    safe_print("说明     = %s" % row.detail)
    safe_print("")

    if row.status == "ok":
        safe_print("【结论】副本健康: 只从正本取数, 内容一致。")
        return 0

    safe_print("【结论】副本**有问题**(status=%s) ⇒ 需要按资产重建副本。" % row.status)
    safe_print(
        "       重建路径: 迁移 current_schema_20261225_rebuild_identity_candidates_copy"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
