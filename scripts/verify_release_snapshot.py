#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版后**验收快照** —— 把「这次到底上线了什么」变成一份可归档的证据(只读)。

为什么要有这个脚本
------------------
发版脚本只回答「镜像起没起来、迁移跑没跑」, **不回答**「业务状态对不对」。
而后者才是回归的真正目标:

* 迁移版本到底停在哪个 revision?
* 候选集副本是不是真的改成「从正本取数」了?
* 语义层「认不出店」的逐月占比是什么样? 新增月份是不是 0?

⇒ 这个脚本把这几项**一次性采集**成一份 JSON 快照, 可贴进发版记录、可留档比对。

口径 SSOT
---------
⚠️ **不另写一份判定** —— 快照里的每个数字都来自巡检自己的函数:

* 候选集副本健康 → :func:`collect_identity_candidates_copy`
* 逐月 unknown → :func:`collect_semantic_resolution`
* 生效日 / 阈值 → :func:`resolve_alignment_effective_date` /
  :func:`resolve_semantic_unknown_rate_threshold`

⇒ 快照看到的 = 巡检会判的, **不会分叉**。

安全边界
--------
1. **只读** —— 全程只有 ``SELECT``;
2. 连接串**只从环境变量读**, 源码里**零字面量**;
3. 解析用 ``sqlalchemy.engine.make_url()``;
4. 输出**脱敏**(只留 driver/host/port/库名, 绝不含口令)。

用法
----
::

    python scripts/verify_release_snapshot.py --output output/release-snapshot.json

退出码
------
``0`` = 快照采集完成且**全部关键项通过`` / ``1`` = 有关键项不通过 / ``2`` = 参数或连接有问题。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from backend.utils.project_env import load_project_env  # noqa: E402

# ⚠️ **必须先加载 .env 再 import 数据库模块** ——
# ``backend.models.database`` 在 import 时就会按 ``DATABASE_URL`` 建引擎。
load_project_env(_PROJECT_ROOT, profile="collection")

from backend.models.database import get_async_database_url  # noqa: E402
from backend.services.data_pipeline.cloud_sync_integrity_service import (  # noqa: E402
    collect_identity_candidates_copy,
    collect_semantic_resolution,
    resolve_alignment_effective_date,
    resolve_semantic_unknown_rate_threshold,
)
from backend.tasks.cloud_sync_integrity_tasks import (  # noqa: E402
    resolve_cloud_database_url_from_env,
)

#: 迁移版本戳表(与 alembic-current.ini 的 version_table 一致)。
VERSION_TABLE = "public.current_schema_alembic_version"


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


async def _collect(url: str) -> dict:
    engine = create_async_engine(get_async_database_url(url))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        version = None
        try:
            version = (
                await db.execute(
                    text("SELECT version_num FROM {table}".format(table=VERSION_TABLE))
                )
            ).scalar_one_or_none()
        except Exception as exc:  # noqa: BLE001 - 快照不能因为这张表就整个失败
            version = "(unavailable: %s)" % exc

        effective_date = resolve_alignment_effective_date()
        threshold = resolve_semantic_unknown_rate_threshold()
        copy_row = await collect_identity_candidates_copy(db)
        month_rows = await collect_semantic_resolution(
            db,
            alignment_effective_date=effective_date,
            threshold=threshold,
        )
        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "migration_version": version,
            "alignment_effective_date": (
                effective_date.isoformat() if effective_date else None
            ),
            "semantic_unknown_rate_threshold": threshold,
            "candidates_copy": copy_row.to_dict() if copy_row is not None else None,
            "semantic_months": [row.to_dict() for row in month_rows],
        }
    finally:
        await db.close()
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="采集一份发版后验收快照(只读, 口径复用巡检)"
    )
    parser.add_argument(
        "--target",
        choices=["cloud", "local"],
        default="cloud",
        help="看云端(默认)还是本地",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default="",
        help="把快照写成 JSON(默认只打印)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    url = _resolve_target(args.target)
    payload = asyncio.run(_collect(url))
    payload["target"] = _masked_target(url)

    copy_row = payload.get("candidates_copy")
    degraded_months = [
        row["month_start"]
        for row in payload["semantic_months"]
        if row.get("status") == "degraded"
    ]

    safe_print("目标            = %s" % payload["target"])
    safe_print("采集时间        = %s" % payload["collected_at"])
    safe_print("迁移版本        = %s" % payload["migration_version"])
    safe_print(
        "对齐生效日      = %s" % (payload["alignment_effective_date"] or "(未配置)")
    )
    safe_print("unknown 阈值    = %.4f" % payload["semantic_unknown_rate_threshold"])
    safe_print("")
    safe_print("候选集副本      = %s" % (copy_row or {}).get("status", "(不适用)"))
    safe_print("  从正本取数    = %s" % ((copy_row or {}).get("reads_source", "?")))
    safe_print(
        "  副本/正本行数 = %s / %s"
        % (
            (copy_row or {}).get("copy_rows", "?"),
            (copy_row or {}).get("source_rows", "?"),
        )
    )
    safe_print(
        "  仅正本有/仅副本有 = %s / %s"
        % (
            (copy_row or {}).get("view_only_rows", "?"),
            (copy_row or {}).get("copy_only_rows", "?"),
        )
    )
    safe_print("")
    safe_print("逐月 unknown:")
    for row in payload["semantic_months"]:
        safe_print(
            "  %-12s %6s %6s %7.2f%%  %-14s %s"
            % (
                row["month_start"],
                row["total_rows"],
                row["unknown_rows"],
                row["unknown_rate"] * 100,
                row["bucket"],
                row["status"],
            )
        )
    safe_print("")
    if degraded_months:
        safe_print(
            "【结论】%d 个月超阈值: %s"
            % (len(degraded_months), ", ".join(degraded_months))
        )
    else:
        safe_print("【结论】没有月份超阈值。")
    if copy_row is not None and copy_row.get("status") != "ok":
        safe_print("【结论】候选集副本状态 = %s(期望 ok)" % copy_row.get("status"))

    if args.output_path:
        path = Path(args.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        safe_print("快照已存档: %s" % path)

    healthy = not degraded_months and (
        copy_row is None or copy_row.get("status") == "ok"
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
