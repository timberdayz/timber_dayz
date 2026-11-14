#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""漂移判定口径的**离线回放**(2026-11-14 口径回退的影响面评估)。

为什么需要它
------------

2026-11-14 把「多一列 ⇒ 阻断」回退成「多一列 ⇒ 不阻断」
(对齐 2026-11-07 规格 §1.4)。这是**业务口径变更**, 不是纯 bug 修复 ⇒
上线前必须先知道它对**存量文件**的影响面:

* 多少文件从「被阻断」变成「可放行」(收益);
* 多少文件反而从「可放行」变成「被阻断」(代价 —— 典型来源是
  「该维度尚未定义核心字段清单」的 B1 口径);
* 分别落在哪些维度上。

怎么做到「同一份事实、两套口径」
--------------------------------

脚本对每个文件跑**一次** ``get_file_sync_readiness``(那会调用生产代码里的
``classify_drift``), 但用 ``mock.patch`` 把 L3 判定入口替换成
**2026-11-13 的旧口径快照**, 再跑一遍 —— 于是两次跑的是**同一批文件、
同一批表头**, 唯一差别就是判定口径。

[*] patch 目标必须打在使用方的**模块属性**上
----------------------------------------------
``template_matcher`` 与 ``data_sync_template_status_service`` 都是
``from ... import classify_drift``(模块级持有函数对象引用) ⇒
只 patch ``data_sync_status_semantics.classify_drift`` **不生效**,
两次跑出来会一模一样, 报告会显示「结论全部不变」—— 那是**假象**。
所以本脚本同时 patch 这两个使用方, 并在开头做**自检**。

旧口径快照刻意**只保留差异部分**: 2026-11-13 与 2026-11-14 的唯一分歧是
「多出来的列算不算阻断」(以及少列时归因于「没有语义契约」还是
「没有核心字段清单」)。它只用于**离线对比**, 不参与任何运行时路径。

只读保证
--------

本脚本**只读**: 不写业务库, 不改文件状态, 不触发重检。

用法
----

    python scripts/replay_drift_caliber.py                 # 全量
    python scripts/replay_drift_caliber.py --limit 50      # 抽样
    python scripts/replay_drift_caliber.py --json          # 机器可读输出
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 旧口径快照(2026-11-13 v7.26.0)—— **仅用于离线对比**
# ---------------------------------------------------------------------------
def _classify_drift_legacy(**kwargs: Any):
    """2026-11-13 的判定入口快照。

    与现行口径的唯一实质差异:
      * 多出来的列 ⇒ **阻断**(除非用户确认过);
      * 少列时, 只要「无法证明可选」⇒ 阻断(不看清单是否配置)。
    """
    from backend.services.data_sync_status_semantics import (
        GOVERNANCE_STATUS_BREAKING_DRIFT,
        GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
        OPTIONAL_RAW_FIELD_NAMES,
        TEMPLATE_STATUS_ALIAS_ONLY,
        TEMPLATE_STATUS_FORMAT_DRIFT,
        TEMPLATE_STATUS_READY,
        TEMPLATE_STATUS_UPDATE_REQUIRED,
        DriftDecision,
        governance_status_for,
    )

    def _dedupe(values):
        seen = set()
        out = []
        for value in values:
            text = str(value)
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out

    added = _dedupe(kwargs.get("added_fields") or [])
    removed = _dedupe(kwargs.get("removed_fields") or [])
    format_columns = _dedupe(kwargs.get("format_drift_columns") or [])
    missing_required = _dedupe(kwargs.get("missing_required_keys") or [])
    missing_optional = _dedupe(kwargs.get("missing_optional_keys") or [])

    optional_set = {
        str(column)
        for column in (kwargs.get("optional_removed_raw_fields") or [])
        if str(column)
    }
    optional_set.update(
        str(column)
        for column in (kwargs.get("optional_raw_fields") or [])
        if str(column)
    )
    optional_set.update(OPTIONAL_RAW_FIELD_NAMES)

    confirmed_set = {
        str(column)
        for column in (kwargs.get("confirmed_extra_fields") or [])
        if str(column)
    }
    alias_rescued = {
        str(column)
        for column in (kwargs.get("alias_rescued_removed_raw_fields") or [])
        if str(column)
    }

    blocking: List[str] = []
    non_blocking: List[str] = []

    blocking.extend(format_columns)
    blocking.extend(missing_required)

    for column in removed:
        if column in optional_set:
            non_blocking.append(column)
        elif column in alias_rescued:
            non_blocking.append(column)
        else:
            blocking.append(column)

    for column in added:
        if column in confirmed_set:
            non_blocking.append(column)
        else:
            blocking.append(column)

    non_blocking.extend(missing_optional)

    blocking = _dedupe(blocking)
    non_blocking = [item for item in _dedupe(non_blocking) if item not in set(blocking)]

    if format_columns:
        template_status = TEMPLATE_STATUS_FORMAT_DRIFT
        reason = "列名没变但值的形态变了(入库必然整份失败)"
    elif kwargs.get("is_exact_match"):
        template_status = TEMPLATE_STATUS_READY
        reason = "列名与顺序完全一致"
    elif kwargs.get("is_semantic_match"):
        template_status = TEMPLATE_STATUS_ALIAS_ONLY
        reason = "语义完全等价(别名命中), 列名差异不影响入库"
    elif blocking:
        template_status = TEMPLATE_STATUS_UPDATE_REQUIRED
        reason = f"有 {len(blocking)} 项阻断漂移"
    else:
        template_status = TEMPLATE_STATUS_ALIAS_ONLY
        reason = "存在非阻断漂移"

    governance_status = governance_status_for(template_status)
    if governance_status not in {
        GOVERNANCE_STATUS_BREAKING_DRIFT,
        GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    }:
        governance_status = governance_status

    return DriftDecision(
        is_blocking=template_status
        in {TEMPLATE_STATUS_UPDATE_REQUIRED, TEMPLATE_STATUS_FORMAT_DRIFT},
        template_status=template_status,
        governance_status=governance_status,
        blocking_changes=blocking,
        non_blocking_changes=non_blocking,
        reason=reason,
    )


def _is_blocked(readiness: Any) -> bool:
    """该文件此刻是否处于「被模板阻断」。

    ``get_file_sync_readiness`` 与 ``evaluate_catalog_file`` 的键名不同
    (``should_auto_sync`` / ``template_update_required``) ⇒ 两个都认。
    """
    if not isinstance(readiness, dict):
        return False
    if "template_update_required" in readiness:
        return bool(readiness["template_update_required"])
    if "should_auto_sync" in readiness:
        return not bool(readiness["should_auto_sync"])
    return False


def _composition_of(readiness: Any) -> Dict[str, Any]:
    """拆出这个文件此刻的**漂移构成**。

    用途: 证明「结论不变」不是因为脚本失效, 而是因为存量文件里
    **没有「纯多列」**这一类 —— 也就是口径回退唯一会改变结论的那一类。
    """
    empty = {
        "added": [],
        "removed": [],
        "missing_required": [],
        "format_drift": False,
    }
    if not isinstance(readiness, dict):
        return empty
    header_changes = readiness.get("header_changes")
    if not isinstance(header_changes, dict):
        header_changes = {}
    missing_required = (
        readiness.get("missing_required_keys")
        or header_changes.get("missing_required_keys")
        or []
    )
    return {
        "added": list(header_changes.get("added_fields") or []),
        "removed": list(header_changes.get("removed_fields") or []),
        "missing_required": list(missing_required),
        "format_drift": bool(
            header_changes.get("format_drift") or readiness.get("format_drift")
        ),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def _run(limit: Optional[int], as_json: bool) -> int:
    from sqlalchemy import select

    from backend.models.database import AsyncSessionLocal
    from backend.services.data_sync_service import DataSyncService
    from modules.core.db import CatalogFile

    # ── patch 目标: 使用方的模块属性(它们是模块级 import) ──────────────
    PATCH_TARGETS = (
        "backend.services.template_matcher.classify_drift",
        "backend.services.data_sync_template_status_service.classify_drift",
    )

    # ── 自检: 确认 patch 真的生效, 且两套口径确实不同 ─────────────────
    # (patch 目标打错时, 报告会显示「结论全部不变」—— 那是假象。)
    from backend.services.data_sync_status_semantics import classify_drift as _current

    _probe_new = _current(added_fields=["探针列"])
    _probe_old = _classify_drift_legacy(added_fields=["探针列"])
    if _probe_new.is_blocking == _probe_old.is_blocking:
        print(
            "[WARN] 新旧口径对「多一列」的结论相同 —— 对比结果可能没有区分度,"
            " 请确认口径差异是否还在。",
            file=sys.stderr,
        )

    report: Dict[str, Any] = {
        "total": 0,
        "unchanged": 0,
        "blocked_under_old": 0,
        "blocked_under_new": 0,
        "newly_released": 0,
        "newly_blocked": 0,
        "newly_released_by_dimension": {},
        "newly_blocked_by_dimension": {},
        "samples": [],
        "probe_distinct": _probe_new.is_blocking != _probe_old.is_blocking,
        "composition": {
            "with_added": 0,
            "with_removed": 0,
            "with_missing_required": 0,
            "with_format_drift": 0,
            "pure_added": 0,
            "pure_added_blocked_under_old": 0,
            "pure_added_released_under_new": 0,
        },
    }

    try:
        async with AsyncSessionLocal() as db:
            stmt = select(CatalogFile).order_by(CatalogFile.id.desc())
            if limit:
                stmt = stmt.limit(int(limit))
            files = list((await db.execute(stmt)).scalars().all())

            service = DataSyncService(db)

            for catalog_file in files:
                file_id = int(catalog_file.id)
                try:
                    new_readiness = await service.get_file_sync_readiness(
                        file_id, use_template_header_row=True
                    )
                except Exception as exc:  # noqa: BLE001
                    report["samples"].append(
                        {
                            "file_id": file_id,
                            "error": str(exc)[:200],
                        }
                    )
                    continue

                with patch(PATCH_TARGETS[0], _classify_drift_legacy), patch(
                    PATCH_TARGETS[1], _classify_drift_legacy
                ):
                    try:
                        old_readiness = await service.get_file_sync_readiness(
                            file_id, use_template_header_row=True
                        )
                    except Exception as exc:  # noqa: BLE001
                        old_readiness = {"error": str(exc)[:200]}

                report["total"] += 1
                new_blocked = _is_blocked(new_readiness)
                old_blocked = _is_blocked(old_readiness)

                # ── 漂移构成统计: 证明「结论不变」不是脚本失效造成的假象 ────
                composition = _composition_of(new_readiness)
                comp = report["composition"]
                added = composition["added"]
                removed = composition["removed"]
                missing_required = composition["missing_required"]
                format_drift = composition["format_drift"]
                if added:
                    comp["with_added"] += 1
                if removed:
                    comp["with_removed"] += 1
                if missing_required:
                    comp["with_missing_required"] += 1
                if format_drift:
                    comp["with_format_drift"] += 1
                # 「纯多列」= 只多了列, 没有少列 / 没有必填语义键缺失 / 没有形态漂移
                # —— 这正是口径回退唯一会改变结论的那一类文件。
                pure_added = bool(added) and not (
                    removed or missing_required or format_drift
                )
                if pure_added:
                    comp["pure_added"] += 1
                    if old_blocked:
                        comp["pure_added_blocked_under_old"] += 1
                    if not new_blocked:
                        comp["pure_added_released_under_new"] += 1

                if new_blocked:
                    report["blocked_under_new"] += 1
                if old_blocked:
                    report["blocked_under_old"] += 1
                if new_blocked == old_blocked:
                    report["unchanged"] += 1
                    continue

                dimension = "{}/{}/{}".format(
                    getattr(catalog_file, "platform_code", None),
                    getattr(catalog_file, "data_domain", None),
                    getattr(catalog_file, "granularity", None),
                )
                if old_blocked and not new_blocked:
                    report["newly_released"] += 1
                    bucket = report["newly_released_by_dimension"]
                    bucket[dimension] = bucket.get(dimension, 0) + 1
                else:
                    report["newly_blocked"] += 1
                    bucket = report["newly_blocked_by_dimension"]
                    bucket[dimension] = bucket.get(dimension, 0) + 1

                if len(report["samples"]) < 50:
                    report["samples"].append(
                        {
                            "file_id": file_id,
                            "file_name": getattr(catalog_file, "file_name", None),
                            "dimension": dimension,
                            "old_blocked": old_blocked,
                            "new_blocked": new_blocked,
                            "old_reason": (old_readiness or {}).get("update_reason"),
                            "new_reason": (new_readiness or {}).get("update_reason"),
                        }
                    )
    finally:
        # ``async with AsyncSessionLocal()`` 已负责关闭会话。
        pass

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("漂移口径离线回放(旧口径 = 2026-11-13 / 新口径 = 2026-11-14)")
        print("=" * 72)
        print(f"评估文件数: {report['total']}")
        print(f"结论不变  : {report['unchanged']}")
        print(f"旧口径阻断: {report['blocked_under_old']}")
        print(f"新口径阻断: {report['blocked_under_new']}")
        print(f"新口径放行: {report['newly_released']}   (旧口径阻断 → 新口径可入库)")
        print(f"新口径阻断: {report['newly_blocked']}   (旧口径可入库 → 新口径阻断)")
        comp = report["composition"]
        print("\n-- 漂移构成(证明「结论不变」不是脚本失效) --")
        print(f"  两套口径对「多一列」结论不同: {report['probe_distinct']}")
        print(f"  含新增列的文件  : {comp['with_added']}")
        print(f"  含缺失列的文件  : {comp['with_removed']}")
        print(f"  必填语义键缺失  : {comp['with_missing_required']}")
        print(f"  值形态漂移      : {comp['with_format_drift']}")
        print(f"  纯多列文件      : {comp['pure_added']}")
        print(f"    其中旧口径阻断 : {comp['pure_added_blocked_under_old']}")
        print(f"    其中新口径放行 : {comp['pure_added_released_under_new']}")
        if report["newly_released_by_dimension"]:
            print("\n-- 新放行的维度分布 --")
            for key, value in sorted(
                report["newly_released_by_dimension"].items(), key=lambda kv: -kv[1]
            ):
                print(f"  {key}: {value}")
        if report["newly_blocked_by_dimension"]:
            print("\n-- 新阻断的维度分布(需要重点看!) --")
            for key, value in sorted(
                report["newly_blocked_by_dimension"].items(), key=lambda kv: -kv[1]
            ):
                print(f"  {key}: {value}")
        if report["samples"]:
            print("\n-- 样例 --")
            for item in report["samples"][:20]:
                if "error" in item:
                    print(f"  file_id={item['file_id']} 读取失败: {item['error']}")
                    continue
                print(
                    f"  file_id={item['file_id']} {item.get('dimension')} "
                    f"旧阻断={item['old_blocked']} 新阻断={item['new_blocked']}"
                )
                print(f"      旧: {item.get('old_reason')}")
                print(f"      新: {item.get('new_reason')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="漂移判定口径离线回放(只读)")
    parser.add_argument("--limit", type=int, default=None, help="只评估最近 N 个文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    from backend.utils.project_env import load_project_env

    load_project_env(REPO_ROOT)
    return asyncio.run(_run(args.limit, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
