#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性回填脚本：补齐 ``public.catalog_files`` 的店铺账号身份（Task 9 Step 4b/5）。

背景
----
``public.catalog_files.shop_account_id`` 实测只有 87/460 有值，而 ``platform_shop_id``
在文件层 0/460 完全不可用。``data_hash`` 的去重作用域要用到稳定身份编号，
所以**必须先把文件层的身份补齐**，再切口径。

口径（与采集登记路径一致）
-------------------------
1. 采集上下文里已知的 ``shop_account_id``（``.meta.json`` 的 ``collection_info`` /
   ``business_metadata``，或调用方直接给出）—— **主路径**；
2. 否则按 (平台, 平台店铺ID / 店铺标签) 反查 ``core.shop_accounts``，
   命中唯一才用；
3. 都不是 -> 保持 ``NULL``（**不猜**），并输出待处理清单。

安全约定
--------
- **默认 ``--dry-run``**（只读预览）；必须显式 ``--apply`` 才写。
- ``--apply`` 只 UPDATE ``public.catalog_files`` 的
  ``shop_account_id`` / ``platform_shop_id`` / ``store_name``，**不碰别的表**。
- 幂等：已填好的行不会被重复改写，重复执行结果一致。

口径切换的影响（必须知道再上线）
--------------------------------
作用域里的身份键一旦从 ``shop_id`` 变成 ``shop_account_id``，**同一份数据再采一次
算出的 ``data_hash`` 就和历史行不一样了** -> 会被当成新数据插入（重复入账）。
因此脚本会额外输出「需重建清单」：已经入库、且身份口径会变的文件 id。

重建办法（按文件粒度，不做全量重建）：

1. ``CatalogFileDeleteService.delete_file(file_id)`` —— 连带删掉该文件在
   ``b_class.fact_*`` 里的事实行（按 ``file_id`` 删）；
2. 重新扫描登记（``modules.services.catalog_scanner``）—— 此时 ``shop_account_id``
   已经是回填后的值；
3. 重新入库（``POST /data-platform/field-mapping/ingest``，body 带 ``file_id``）。

注：``data_hash`` 口径切换本身（作用域的键名从 ``scope:shop_id`` 变成
``scope:shop_account_id``）会让**所有**已入库文件的 hash 失效，所以口径切换
实际上要求一次**全量重建**（计划 Task 10 Step 6 给出的补救也是全量重建）。
本脚本的「需重建清单」精确覆盖其中因回填而变身份的那部分。

用法
----
::

    # 只读预览（默认）
    python -m backend.services.catalog_files_identity_backfill --dry-run

    # 真正写库（部署阶段由人统一执行）
    python -m backend.services.catalog_files_identity_backfill --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from modules.services.catalog_scanner import (
    collect_shop_account_candidates,
    load_shop_account_identity_candidates,
    match_shop_account_by_identity,
)

DEFAULT_DATABASE_URL = (
    "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
)

# 目录里表示"没有值"的哨兵
_EMPTY_SENTINELS = {"", "none", "null", "unknown"}


def _text(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_SENTINELS:
        return ""
    return text


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass
class BackfillUpdate:
    """一条待回填的文件记录。"""

    file_id: int
    platform_code: str
    shop_id: str
    store_name: str
    shop_account_id: str
    platform_shop_id: str
    main_account_id: str
    match_method: str
    scope_changed: bool
    already_ingested: bool


@dataclass
class PendingItem:
    """一条待处理（保持 NULL）的记录，按 (平台, 标签) 归并。"""

    platform_code: str
    shop_id: str
    store_name: str
    reason: str
    candidate_count: int
    file_count: int
    file_ids: List[int] = field(default_factory=list)


@dataclass
class BackfillPlan:
    """回填计划（纯数据，不含任何写操作）。"""

    updates: List[BackfillUpdate] = field(default_factory=list)
    pending: List[PendingItem] = field(default_factory=list)
    rebuild_file_ids: List[int] = field(default_factory=list)
    total_rows: int = 0
    already_filled: int = 0
    scope_changing: int = 0

    @property
    def filled_after(self) -> int:
        return self.already_filled + len(self.updates)

    def coverage(self) -> Dict[str, Dict[str, int]]:
        return {
            "before": {
                "total": self.total_rows,
                "filled": self.already_filled,
            },
            "after": {
                "total": self.total_rows,
                "filled": self.filled_after,
            },
        }


def _current_scope_identity(row: Dict[str, Any]) -> str:
    """当前生效的去重作用域身份键取值（与去重服务口径一致）。"""
    for key in ("shop_account_id", "platform_shop_id", "shop_id"):
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _meta_identity(meta_file_path: Optional[str]) -> Dict[str, str]:
    """尽力从 ``.meta.json`` 里读采集上下文身份（文件不在本机时静默跳过）。"""
    path_text = _text(meta_file_path)
    if not path_text:
        return {}
    candidates = [Path(path_text)]
    if not Path(path_text).is_absolute():
        candidates.append(_repo_root() / path_text)
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        collection_info = payload.get("collection_info") or {}
        business_metadata = payload.get("business_metadata") or {}
        merged: Dict[str, str] = {}
        for source in (collection_info, business_metadata):
            if not isinstance(source, dict):
                continue
            for key in (
                "shop_account_id",
                "main_account_id",
                "platform_shop_id",
                "store_name",
                "shop_name",
                "shop_id",
            ):
                value = _text(source.get(key))
                if value and key not in merged:
                    merged[key] = value
        if merged:
            return merged
    return {}


def build_backfill_plan(
    catalog_rows: Iterable[Dict[str, Any]],
    accounts: Iterable[Dict[str, Any]],
    aliases: Iterable[Dict[str, Any]],
    *,
    skip_ingested: bool = False,
) -> BackfillPlan:
    """纯函数：算出回填计划（不碰数据库）。

    Args:
        catalog_rows: ``public.catalog_files`` 的行（dict）
        accounts: ``core.shop_accounts`` 的身份候选
        aliases: ``core.shop_account_aliases`` 的别名候选
        skip_ingested: 为 True 时不动已入库文件（口径零变更，代价是覆盖率更低）

    Returns:
        :class:`BackfillPlan`
    """
    account_rows = list(accounts or [])
    alias_rows = list(aliases or [])
    plan = BackfillPlan()

    pending_index: Dict[Tuple[str, str, str], PendingItem] = {}

    for row in catalog_rows:
        plan.total_rows += 1
        file_id = int(row.get("id") or 0)
        platform_code = _text(row.get("platform_code")).lower()
        source_platform = _text(row.get("source_platform")).lower()
        shop_id = _text(row.get("shop_id"))
        store_name = _text(row.get("store_name"))
        platform_shop_id = _text(row.get("platform_shop_id"))
        status = _text(row.get("status")).lower()
        already_ingested = status == "ingested"

        current_identity = _current_scope_identity(row)
        if current_identity and _text(row.get("shop_account_id")):
            plan.already_filled += 1
            continue

        meta = _meta_identity(row.get("meta_file_path"))
        known_shop_account_id = _text(meta.get("shop_account_id"))
        label_shop_id = shop_id or _text(meta.get("shop_id"))
        label_store_name = store_name or _text(meta.get("store_name")) or _text(
            meta.get("shop_name")
        )
        label_platform_shop_id = platform_shop_id or _text(meta.get("platform_shop_id"))

        matched: Optional[Dict[str, Any]] = None
        candidate_count = 0
        if known_shop_account_id:
            # 主路径：采集上下文里已经带了稳定身份编号
            matched = {
                "shop_account_id": known_shop_account_id,
                "main_account_id": _text(meta.get("main_account_id")) or None,
                "store_name": label_store_name or None,
                "platform_shop_id": label_platform_shop_id or None,
                "match_method": "meta_json",
            }
            candidate_count = 1
        else:
            candidates, _method = collect_shop_account_candidates(
                account_rows,
                alias_rows,
                platform_code=platform_code,
                source_platform=source_platform,
                platform_shop_id=label_platform_shop_id,
                store_name=label_store_name,
                shop_id=label_shop_id,
            )
            candidate_count = len(candidates)
            matched = match_shop_account_by_identity(
                account_rows,
                alias_rows,
                platform_code=platform_code,
                source_platform=source_platform,
                platform_shop_id=label_platform_shop_id,
                store_name=label_store_name,
                shop_id=label_shop_id,
            )

        if not matched:
            key = (platform_code, label_shop_id or label_store_name, label_store_name)
            item = pending_index.get(key)
            if item is None:
                item = PendingItem(
                    platform_code=platform_code,
                    shop_id=label_shop_id,
                    store_name=label_store_name,
                    reason="ambiguous" if candidate_count > 1 else "not_found",
                    candidate_count=candidate_count,
                    file_count=0,
                )
                pending_index[key] = item
            item.file_count += 1
            if file_id:
                item.file_ids.append(file_id)
            continue

        if skip_ingested and already_ingested:
            continue

        new_identity = _text(matched.get("shop_account_id"))
        scope_changed = bool(new_identity) and new_identity != current_identity
        if scope_changed:
            plan.scope_changing += 1

        plan.updates.append(
            BackfillUpdate(
                file_id=file_id,
                platform_code=platform_code,
                shop_id=label_shop_id,
                store_name=label_store_name,
                shop_account_id=new_identity,
                platform_shop_id=_text(matched.get("platform_shop_id")),
                main_account_id=_text(matched.get("main_account_id")),
                match_method=_text(matched.get("match_method")) or "unknown",
                scope_changed=scope_changed,
                already_ingested=already_ingested,
            )
        )

        if scope_changed and already_ingested:
            plan.rebuild_file_ids.append(file_id)

    plan.pending = sorted(
        pending_index.values(),
        key=lambda item: (-item.file_count, item.platform_code, item.shop_id),
    )
    return plan


def _load_catalog_rows(session) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT id, platform_code, source_platform, shop_id, store_name,
                   platform_shop_id, main_account_id, shop_account_id,
                   status, file_metadata, meta_file_path, file_path
              FROM public.catalog_files
             ORDER BY id
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _apply_updates(session, plan: BackfillPlan) -> int:
    """只 UPDATE ``public.catalog_files``（幂等）。"""
    from sqlalchemy import text

    applied = 0
    for update in plan.updates:
        if not update.file_id or not update.shop_account_id:
            continue
        session.execute(
            text(
                """
                UPDATE public.catalog_files
                   SET shop_account_id = :shop_account_id,
                       store_name = COALESCE(NULLIF(:store_name, ''), store_name),
                       platform_shop_id = COALESCE(NULLIF(:platform_shop_id, ''), platform_shop_id)
                 WHERE id = :id
                """
            ),
            {
                "id": update.file_id,
                "shop_account_id": update.shop_account_id,
                "store_name": update.store_name or "",
                "platform_shop_id": update.platform_shop_id or "",
            },
        )
        applied += 1
    session.commit()
    return applied


def _print_report(plan: BackfillPlan, applied: Optional[int]) -> None:
    coverage = plan.coverage()
    before = coverage["before"]
    after = coverage["after"]
    print("=== 覆盖率 ===")
    print(f"before: {before['filled']}/{before['total']}")
    print(f"after : {after['filled']}/{after['total']}")
    print(f"待回填文件数: {len(plan.updates)}")
    print(f"口径会变的文件数: {plan.scope_changing}")
    print(f"需重建(已入库且口径会变)的文件数: {len(plan.rebuild_file_ids)}")
    if plan.rebuild_file_ids:
        preview = plan.rebuild_file_ids[:50]
        print(f"需重建 file_id (前50个): {preview}")
    print()
    print(f"=== 待处理清单(保持 NULL) {len(plan.pending)} 条 ===")
    for item in plan.pending:
        print(
            f"platform={item.platform_code} shop_id={item.shop_id!r} "
            f"store_name={item.store_name!r} files={item.file_count} "
            f"candidates={item.candidate_count} reason={item.reason}"
        )
    print()
    print("=== 匹配方式分布 ===")
    methods: Dict[str, int] = {}
    for update in plan.updates:
        methods[update.match_method] = methods.get(update.match_method, 0) + 1
    for method, count in sorted(methods.items(), key=lambda item: -item[1]):
        print(f"{method}: {count}")
    if applied is not None:
        print()
        print(f"已写入 public.catalog_files: {applied} 行")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="回填 public.catalog_files 的店铺账号身份（默认 --dry-run）"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL") or os.getenv("DEFAULT_DATABASE_URL") or DEFAULT_DATABASE_URL,
        help="数据库连接串（默认取环境变量 DATABASE_URL）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（默认只读预览 --dry-run）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读预览（默认行为）",
    )
    parser.add_argument(
        "--skip-ingested",
        action="store_true",
        help="不动已入库的文件（口径零变更，覆盖率更低）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="只处理前 N 行（调试用，0 = 全部）",
    )
    parser.add_argument(
        "--report-out",
        default="",
        help="把报告写成 JSON 文件的路径（可选）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    apply_mode = bool(args.apply) and not args.dry_run

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    engine = sa.create_engine(args.database_url, future=True)
    session = Session(engine)
    try:
        accounts, aliases = load_shop_account_identity_candidates(session)
        catalog_rows = _load_catalog_rows(session)
    finally:
        session.close()

    if args.limit:
        catalog_rows = catalog_rows[: args.limit]

    plan = build_backfill_plan(
        catalog_rows,
        accounts,
        aliases,
        skip_ingested=bool(args.skip_ingested),
    )

    applied: Optional[int] = None
    if apply_mode:
        session = Session(engine)
        try:
            applied = _apply_updates(session, plan)
        finally:
            session.close()

    _print_report(plan, applied)

    if args.report_out:
        report = {
            "coverage": plan.coverage(),
            "updates": [update.__dict__ for update in plan.updates],
            "pending": [item.__dict__ for item in plan.pending],
            "rebuild_file_ids": plan.rebuild_file_ids,
            "applied": applied,
        }
        Path(args.report_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"报告已写入: {args.report_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
