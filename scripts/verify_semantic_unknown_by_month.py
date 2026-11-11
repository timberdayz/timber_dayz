#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐月看语义层的「认不出店」占比（**只读**）。

为什么有这个脚本
----------------
「新增月份认不出 = 0」这件事**已经自动化**了 ——
:mod:`backend.services.data_pipeline.cloud_sync_integrity_service` 里的
``cloud-sync-integrity-check-hourly`` 巡检每小时第 37 分跑一次,
按「对齐生效日」分档, 占比超阈值就报警。

但有两件事它答不了:

1. **该配哪个生效日?** 分档是**按月**的(生效日所在月整月算「新问题」档),
   而 2026-11 的事故就在**云端** ⇒ 必须先看到云端**逐月**的真实数字才能定。
   本地库干净不代表云端干净。
2. **配完之后第一份报告长什么样?** 配完不该直接放手,
   得先确认「该报警的月份确实干净、不该报警的月份确实被归为历史遗留」。

⇒ 本脚本就是把这两件事变成**一条命令**。

口径 SSOT
---------
⚠️ **不另写一份 SQL / 不另写一份分档规则** —— 脚本直接调用巡检自己的
``collect_semantic_resolution``(逐月统计 + 按月分档),
阈值与生效日的读取也走巡检那两个函数。
⇒ 脚本看到的数字 = 巡检会判的数字, **不会分叉**。

安全边界
--------
1. **只读** —— 全程只有 ``SELECT``;
2. 连接串**只从环境变量读** (``CLOUD_DATABASE_URL`` / ``DATABASE_URL``),
   源码里**零字面量**;
3. 解析用 ``sqlalchemy.engine.make_url()``;
4. 云端连接串的地址规整(容器里的回环地址、隧道开关)**复用巡检那个函数**
   ⇒ 与巡检连的是同一个地方。

用法
----
看云端(默认)::

    python scripts/verify_semantic_unknown_by_month.py

看本地::

    python scripts/verify_semantic_unknown_by_month.py --target local

按某个生效日分档(默认读 ``SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE``)::

    python scripts/verify_semantic_unknown_by_month.py --effective-date 2026-12-01

存档一份 JSON(验收用)::

    python scripts/verify_semantic_unknown_by_month.py --json output/semantic-unknown-20261111.json

退出码
------
``0`` = 没有月份超阈值(干净) / ``1`` = 有月份超阈值(需要处理) / ``2`` = 参数或连接有问题。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from backend.models.database import get_async_database_url  # noqa: E402
from backend.services.data_pipeline.cloud_sync_integrity_service import (  # noqa: E402
    collect_semantic_resolution,
    resolve_alignment_effective_date,
    resolve_semantic_unknown_rate_threshold,
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
    """把连接串压成**脱敏**目标串(只留驱动/主机/端口/库名, 绝不含口令)。"""
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


def _parse_effective_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise SystemExit("--effective-date 格式非法(应为 YYYY-MM-DD): %r" % raw)


async def _collect(
    url: str, effective_date: date | None, threshold: float
) -> list[Any]:
    engine = create_async_engine(get_async_database_url(url))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        return await collect_semantic_resolution(
            db,
            alignment_effective_date=effective_date,
            threshold=threshold,
        )
    finally:
        await db.close()
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="逐月看语义层的「认不出店」占比(只读, 复用巡检口径)"
    )
    parser.add_argument(
        "--target",
        choices=["cloud", "local"],
        default="cloud",
        help="看云端(默认)还是本地",
    )
    parser.add_argument(
        "--effective-date",
        default="",
        help="按这个生效日分档(默认读环境变量 SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="unknown 占比阈值(默认读环境变量, 再默认 0.05)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default="",
        help="把结果写成 JSON(存档用)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    effective_date = (
        _parse_effective_date(args.effective_date)
        if args.effective_date
        else resolve_alignment_effective_date()
    )
    threshold = (
        args.threshold
        if args.threshold is not None
        else resolve_semantic_unknown_rate_threshold()
    )

    url = _resolve_target(args.target)
    rows = asyncio.run(_collect(url, effective_date, threshold))

    safe_print("目标       = %s" % _masked_target(url))
    safe_print(
        "生效日     = %s"
        % (
            effective_date.isoformat()
            if effective_date
            else "(未配置 ⇒ 全部归历史遗留)"
        )
    )
    safe_print("阈值       = %.4f" % threshold)
    safe_print("")
    safe_print(
        "%-12s %8s %9s %8s  %-14s %s"
        % ("月份", "总行", "unknown", "占比", "分档", "状态")
    )
    degraded: list[Any] = []
    for row in rows:
        safe_print(
            "%-12s %8d %9d %7.2f%%  %-14s %s"
            % (
                row.month_start,
                row.total_rows,
                row.unknown_rows,
                row.unknown_rate * 100,
                row.bucket,
                row.status,
            )
        )
        if row.status == "degraded":
            degraded.append(row)

    safe_print("")
    if effective_date is None:
        safe_print(
            "【结论】生效日**未配置** ⇒ 所有月份都归「已知历史遗留」, 巡检**不会报警**。"
        )
        safe_print("       ⇒ 要让「新增月份认不出」有人看见, 必须先配对齐生效日。")
    elif degraded:
        safe_print(
            "【结论】%d 个月超阈值(标 degraded) ⇒ 这几个月**会被报警**。"
            % len(degraded)
        )
        for row in degraded:
            safe_print(
                "       %s: %d/%d 行认不出(%.2f%%)"
                % (
                    row.month_start,
                    row.unknown_rows,
                    row.total_rows,
                    row.unknown_rate * 100,
                )
            )
    else:
        safe_print("【结论】没有月份超阈值 ⇒ 按当前生效日, 巡检是安静的。")

    if args.json_path:
        payload = {
            "target": _masked_target(url),
            "alignment_effective_date": (
                effective_date.isoformat() if effective_date else None
            ),
            "threshold": threshold,
            "months": [
                {
                    "month_start": row.month_start.isoformat(),
                    "total_rows": row.total_rows,
                    "unknown_rows": row.unknown_rows,
                    "unknown_rate": row.unknown_rate,
                    "bucket": row.bucket,
                    "status": row.status,
                }
                for row in rows
            ],
            "degraded_months": [row.month_start.isoformat() for row in degraded],
        }
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        safe_print("已存档: %s" % path)

    return 1 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
