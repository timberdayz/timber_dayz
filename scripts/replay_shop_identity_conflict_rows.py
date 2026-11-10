#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手工重发**同步侧矛盾行**（批次 4.3）。

为什么有这个脚本
----------------
同步侧把**被跳过 / 被降级**的行记进了 ``ops.shop_identity_conflict_rows``
（矛盾行台账）。台账里绝大多数行标着「**已知历史遗留**」—— 按既定决策
「历史数据不修」，那些行的归属**永远不会被修**，也就**不该**被重发。

真正需要人处理的是标着「**待人工处理**」的行：它们的业务日期在
「店铺身份登记信息对齐生效日」之后 ⇒ 台账修好之后**可以**补发。

安全边界（**逐条都是硬约束**）
------------------------------
1. **默认 ``--dry-run``** —— 只预览「将要重发什么」，**不改动任何东西**。
   真要执行必须显式加 ``--execute``；
2. **只处理「待人工处理」的行** —— ``--status`` 默认就是 ``pending_manual``；
3. **默认不动「已知历史遗留」** —— 要动必须**同时**显式给
   ``--status known_legacy`` **和** ``--include-known-legacy``（历史不修）；
4. **不回退同步检查点**、**不重推整表** —— 只**逐行**补发台账里点名的那些行，
   检查点一个字都不动（既定决策：❌ 不回退同步检查点、不重推 11 月）；
5. **不修历史** —— 本脚本只重发**行**，不碰任何事实行的身份戳；
6. **连接串只从环境变量读**（``DATABASE_URL`` / ``CLOUD_DATABASE_URL``），
   源码里**零字面量**；解析用 ``sqlalchemy.engine.make_url()``；
7. **重发仍走既有的身份闸门** —— 补发的行会**再过一次**本地/云端双基准判定；
   台账还没修好的行**照样被拒**（这正是我们要的行为：宁可不补发，也不写错归属）。

用法
----
先看要重发什么（**不改动任何东西**）::

    python scripts/replay_shop_identity_conflict_rows.py --dry-run

按源表与日期范围筛::

    python scripts/replay_shop_identity_conflict_rows.py \\
        --dry-run \\
        --source-table fact_shopee_products_daily \\
        --date-from 2026-11-01 --date-to 2026-11-30 \\
        --limit 50

确认无误后真执行::

    python scripts/replay_shop_identity_conflict_rows.py --execute

⚠️ 真执行会把这些行**写进云端** ⇒ 请先用 ``--dry-run`` 确认清单。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from backend.services.cloud_b_class_mirror_manager import (  # noqa: E402
    build_canonical_columns,
)
from backend.services.cloud_b_class_sync_service import (  # noqa: E402
    SQLAlchemyCloudWriter,
    build_sync_payload,
)
from backend.services.cloud_b_class_sync_utils import (  # noqa: E402
    quote_ident,
    validate_b_class_table_name,
)
from backend.services.shop_identity_conflict_ledger_service import (  # noqa: E402
    STATUS_KNOWN_LEGACY,
    STATUS_PENDING_MANUAL,
    select_conflict_rows,
)


#: 本脚本在 ``ops.shop_identity_conflict_rows`` 里留下的处理备注前缀。
RESOLUTION_NOTE_PREFIX = "replayed via scripts/replay_shop_identity_conflict_rows.py"

#: 重发成功后写入台账的处理状态。
RESOLUTION_STATUS = "resolved"


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


def _load_source_rows(
    engine,
    *,
    source_table_name: str,
    source_row_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """按主键把源行读出来(读**本地** ``b_class`` 表)。

    ⚠️ 表名来自台账, 仍然走 :func:`validate_b_class_table_name` 校验 ⇒
    拼进 SQL 之前先挡住非法表名。

    ⚠️ **必须把主键一起 SELECT 出来** —— 下面的映射键靠它。
    只取 canonical 列的话, 真库只会返回那些列(``id`` 不在其中)⇒
    ``mapping.get("id")`` 恒为 ``None`` ⇒ 映射键全变成 ``"None"``
    ⇒ 每一行都会被误判成「源行已不存在」, 重发**一行都发不出去**。
    (假引擎不校验 SELECT 列 ⇒ 单测全绿也测不出来 —— 真库实测才发现。)
    """
    validate_b_class_table_name(source_table_name)
    if not source_row_ids:
        return {}

    columns = ", ".join(
        quote_ident(column) for column in ("id",) + build_canonical_columns()
    )
    placeholders = ", ".join(
        ":row_id_%d" % index for index in range(len(source_row_ids))
    )
    sql = "SELECT %s FROM b_class.%s WHERE id IN (%s)" % (
        columns,
        quote_ident(source_table_name),
        placeholders,
    )
    params = {"row_id_%d" % index: value for index, value in enumerate(source_row_ids)}
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = result.fetchall()

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        key = str(mapping.get("id"))
        output[key] = mapping
    return output


def _update_resolution(
    engine,
    *,
    conflict_id: Any,
    handled_by: str,
    note: str,
) -> None:
    """把台账行标成「已处理」(人工处理状态 + 处理人 + 处理时间)。"""
    sql = """
    UPDATE ops.shop_identity_conflict_rows
       SET resolution_status = :resolution_status,
           resolved_by = :resolved_by,
           resolved_at = :resolved_at,
           resolution_note = :resolution_note,
           updated_at = :resolved_at
     WHERE id = :conflict_id
    """
    with engine.begin() as conn:
        conn.execute(
            text(sql),
            {
                "resolution_status": RESOLUTION_STATUS,
                "resolved_by": handled_by,
                "resolved_at": datetime.now(timezone.utc),
                "resolution_note": note,
                "conflict_id": conflict_id,
            },
        )


def _describe(row: dict[str, Any]) -> str:
    """一行台账的人读摘要。"""
    accounts = row.get("resolved_accounts")
    if isinstance(accounts, str):
        accounts = [accounts]
    account_text = "、".join(str(item) for item in (accounts or [])) or "(无)"
    return "  - id=%s 表=%s 日期=%s 原因=%s 状态=%s 次数=%s " "行内值=%s 账号=%s" % (
        row.get("id"),
        row.get("source_table_name"),
        row.get("business_date") or "(空)",
        row.get("reason_code"),
        row.get("status"),
        row.get("occurrence_count"),
        row.get("identity_value") or "(空)",
        account_text,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="手工重发同步侧矛盾行（默认 --dry-run，只预览不改动）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览将要重发的行（**默认行为**）",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真的重发（会把这些行写进云端）",
    )
    parser.add_argument(
        "--source-table",
        action="append",
        default=None,
        help="按源表筛选（可重复）",
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help=(
            "按台账状态筛选（可重复）。默认只处理 %s；"
            "%s 需要额外显式 --include-known-legacy"
            % (STATUS_PENDING_MANUAL, STATUS_KNOWN_LEGACY)
        ),
    )
    parser.add_argument(
        "--reason-code",
        action="append",
        default=None,
        help="按原因码筛选（可重复）",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        help="业务日期下界（YYYY-MM-DD，含）",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="业务日期上界（YYYY-MM-DD，含）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理多少行（0 = 不限）",
    )
    parser.add_argument(
        "--include-known-legacy",
        action="store_true",
        help=("显式允许重发「已知历史遗留」的行（历史不修 ⇒ 默认禁止）"),
    )
    parser.add_argument(
        "--handled-by",
        default="",
        help="处理人（默认取当前系统用户）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    execute = bool(args.execute)
    if execute and args.dry_run:
        safe_print("[FAIL] --dry-run 与 --execute 不能同时给")
        return 2

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    cloud_database_url = (os.getenv("CLOUD_DATABASE_URL") or "").strip()
    if not database_url:
        safe_print("[FAIL] 没有 DATABASE_URL（本地库连接串只从环境变量读）")
        return 2
    if not cloud_database_url:
        safe_print("[FAIL] 没有 CLOUD_DATABASE_URL（云端库连接串只从环境变量读）")
        return 2

    statuses = list(args.status or [STATUS_PENDING_MANUAL])
    includes_known_legacy = STATUS_KNOWN_LEGACY in statuses
    if includes_known_legacy and not args.include_known_legacy:
        safe_print(
            "[FAIL] 「已知历史遗留」的行按既定决策**不修**。"
            "要重发它们必须显式加 --include-known-legacy。"
        )
        return 2

    handled_by = (args.handled_by or "").strip() or _default_handler()

    local_engine = create_engine(database_url)
    cloud_engine = create_engine(cloud_database_url)
    try:
        safe_print("[INFO] 本地库: %s" % _masked_target(database_url))
        safe_print("[INFO] 云端库: %s" % _masked_target(cloud_database_url))

        selected: list[dict[str, Any]] = []
        for source_table in args.source_table or [None]:
            rows = select_conflict_rows(
                local_engine,
                source_table_name=source_table,
                statuses=statuses,
                date_from=args.date_from,
                date_to=args.date_to,
                reason_codes=args.reason_code,
                limit=args.limit if args.limit > 0 else None,
            )
            selected.extend(rows)

        # 同一行可能被多个源表筛选命中 ⇒ 按台账主键去重。
        unique: dict[Any, dict[str, Any]] = {}
        for row in selected:
            unique[row.get("id")] = row
        selected = list(unique.values())

        if not selected:
            safe_print("[INFO] 没有匹配的台账行（状态=%s）" % "、".join(statuses))
            if STATUS_PENDING_MANUAL in statuses:
                safe_print(
                    "[提示] 若目标行是「已知历史遗留」，"
                    "请显式加 --status %s --include-known-legacy；"
                    "若全部都是历史遗留，说明对齐生效日尚未配置。" % STATUS_KNOWN_LEGACY
                )
            return 0

        safe_print(
            "[INFO] 匹配到 %d 行（状态=%s）" % (len(selected), "、".join(statuses))
        )
        for row in selected:
            safe_print(_describe(row))

        if not execute:
            safe_print(
                "[DRY-RUN] 以上 %d 行**不会**被改动。"
                "确认无误后加 --execute 真执行。" % len(selected)
            )
            return 0

        safe_print("[EXECUTE] 开始重发 %d 行 …" % len(selected))
        written, refused, missing = _replay_rows(
            local_engine,
            cloud_engine,
            selected,
            handled_by=handled_by,
        )
        safe_print(
            "[DONE] 重发完成：成功 %d 行 / 仍被拒 %d 行 / 源行已不存在 %d 行"
            % (written, refused, missing)
        )
        if refused:
            safe_print(
                "[提示] 仍被拒的行说明**台账还没修好** —— "
                "请先对齐登记信息，再重跑本脚本。"
            )
        return 0
    finally:
        local_engine.dispose()
        cloud_engine.dispose()


def _default_handler() -> str:
    """默认处理人 —— 当前系统用户（取不到就写 ``unknown``）。"""
    try:
        import getpass

        return getpass.getuser() or "unknown"
    except Exception:  # pragma: no cover - 取不到用户不致命
        return "unknown"


def _replay_rows(
    local_engine,
    cloud_engine,
    selected: list[dict[str, Any]],
    *,
    handled_by: str,
) -> tuple[int, int, int]:
    """逐行重发。

    ⚠️ **逐行**重发 —— 不回退检查点、不重推整表。
    ⚠️ 重发**仍然过**既有的身份闸门（本地/云端双基准）⇒ 台账没修好的行照样被拒。
    """
    from backend.services.cloud_b_class_auto_sync_factory import (
        _load_identity_index,
    )
    from backend.services.cloud_sync_identity_guard_service import (
        load_cloud_identity_registry,
    )

    identity_index = _load_identity_index(local_engine)
    cloud_registry = load_cloud_identity_registry()

    writer = SQLAlchemyCloudWriter(
        cloud_engine,
        identity_index=identity_index,
        cloud_registry=cloud_registry,
    )

    written = 0
    refused = 0
    missing = 0

    # 按源表分组 ⇒ 每张表只读一次源行。
    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        by_table.setdefault(str(row.get("source_table_name") or ""), []).append(row)

    for source_table, rows in by_table.items():
        source_row_ids = [
            str(row.get("source_row_id"))
            for row in rows
            if row.get("source_row_id") is not None
        ]
        try:
            source_rows = _load_source_rows(
                local_engine,
                source_table_name=source_table,
                source_row_ids=source_row_ids,
            )
        except Exception as exc:  # noqa: BLE001 —— 单表读失败不终止整批
            safe_print("[WARN] 读源表 %s 失败: %s" % (source_table, exc))
            missing += len(rows)
            continue

        for row in rows:
            source_row_id = str(row.get("source_row_id"))
            source_row = source_rows.get(source_row_id)
            if source_row is None:
                safe_print(
                    "[SKIP] 源行已不存在: %s id=%s" % (source_table, source_row_id)
                )
                missing += 1
                continue

            payload = build_sync_payload(source_row)
            data_domain = str(payload.get("data_domain") or "")
            result = writer(source_table, [payload], data_domain)
            wrote = int(result.get("written_rows") or 0)
            if wrote > 0:
                written += 1
                safe_print("[OK] 已重发 %s id=%s" % (source_table, source_row_id))
                _update_resolution(
                    local_engine,
                    conflict_id=row.get("id"),
                    handled_by=handled_by,
                    note="%s (%s)" % (RESOLUTION_NOTE_PREFIX, data_domain),
                )
            else:
                refused += 1
                safe_print(
                    "[REFUSED] 仍被拒 %s id=%s（冲突 %s / 降级 %s）—— 台账还没修好"
                    % (
                        source_table,
                        source_row_id,
                        result.get("identity_conflict_rows"),
                        result.get("identity_registry_mismatch_rows"),
                    )
                )

    return written, refused, missing


if __name__ == "__main__":
    raise SystemExit(main())
