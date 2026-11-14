#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板发布的**闭环指标**: 发布后 T 分钟内, 受影响文件完成重估的比例。

指标是什么
----------
一次模板变更的完成标准不是「新模板已保存」, 而是「**受它影响的文件已经
重新评估过**」(见 :mod:`backend.services.template_recheck_service`)。
这个脚本就把那句话变成一个**可核查的数字**:

    闭环比例 = (发布后 T 分钟内完成重估的受影响文件数) / (受影响文件总数)

数据来源
--------
* **发布事件** = 模板表里的**一行**。保存模板 = 「归档旧版本 + 插入新版本」,
  新行 id 自增 ⇒ 任何一个模板行都唯一对应一次发布。
  时刻取该行的 ``created_at``。
* **重估记录** = ``catalog_files.file_metadata['auto_ingest']`` 里的
  ``last_recheck_at``(重估时刻)与 ``last_recheck_template_id``
  (重估时生效的模板 id = 对应的发布事件)。

为什么需要 ``last_recheck_template_id``
-------------------------------------
只有「重估时刻」不够 —— 分不清「这次重估是针对哪次发布做的」。
有了它才能把重估记录**归属**到某一次发布。

数据不足时怎么办
----------------
埋点是 2026-11-14(批次 4-2)才加的 ⇒ **存量文件没有这两个字段**。
本脚本会**明确区分**「有埋点但没达标」与「压根没有埋点」,
并把后者单独计数 —— 绝不把「没数据」算成「达标」。

只读保证
--------
本脚本**只读**: 不写业务库, 不改文件状态, 不触发重检。

用法
----
    python scripts/template_release_sla_metric.py
    python scripts/template_release_sla_metric.py --window-minutes 30
    python scripts/template_release_sla_metric.py --since-days 30
    python scripts/template_release_sla_metric.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_iso(raw: Any) -> Optional[datetime]:
    """解析 ISO 时间戳; 拿不到返回 None(宁可算「无数据」也不猜)。"""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _norm(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"N/A", "NA", "None", "null", "NULL"}:
        return None
    return text


def _dimension(row: Any) -> tuple:
    """模板行 / 文件行的维度键(统一成 5 元组)。"""
    return (
        _norm(getattr(row, "platform_code", None) or getattr(row, "platform", None)),
        _norm(getattr(row, "data_domain", None)),
        _norm(getattr(row, "granularity", None)),
        _norm(getattr(row, "sub_domain", None)),
        _norm(getattr(row, "account", None)),
    )


def attribute_rechecks(
    events: List[Dict[str, Any]],
    rechecks: Dict[int, Dict[str, Any]],
    window_minutes: int,
) -> Dict[str, Any]:
    """把重估记录**归属**到发布事件, 并算出闭环比例。

    这是本脚本的**纯逻辑**(不碰数据库), 便于直接单测。

    Args:
        events: 发布事件列表, 每项含 ``template_id`` / ``dimension`` /
            ``published_at``(datetime)。
        rechecks: ``{模板行 id: {"file_id", "rechecked_at", "dimension"}}`` ——
            键是「重估时生效的模板 id」, 即这次重估对应的发布事件。
        window_minutes: 达标窗口(分钟)。

    Returns:
        报告字典(结构见 :func:`_collect` 的返回值)。
    """
    window = timedelta(minutes=window_minutes)
    per_event: List[Dict[str, Any]] = []
    total_affected = 0
    total_on_time = 0
    events_without_data = 0

    for event in events:
        affected = [
            record
            for record in rechecks.values()
            if record["dimension"] == event["dimension"]
        ]
        on_time = [
            record
            for record in affected
            if record["rechecked_at"] - event["published_at"] <= window
        ]
        late = [
            record
            for record in affected
            if record["rechecked_at"] - event["published_at"] > window
        ]
        total_affected += len(affected)
        total_on_time += len(on_time)
        if not affected:
            events_without_data += 1
        per_event.append(
            {
                "template_id": event["template_id"],
                "template_name": event.get("template_name"),
                "version": event.get("version"),
                "status": event.get("status"),
                "dimension": "/".join(part or "-" for part in event["dimension"]),
                "published_at": event["published_at"].isoformat(),
                "affected": len(affected),
                "on_time": len(on_time),
                "late": len(late),
                "ratio": (len(on_time) / len(affected)) if affected else None,
                "late_files": [
                    {
                        "file_id": record["file_id"],
                        "rechecked_at": record["rechecked_at"].isoformat(),
                        "minutes_after_publish": round(
                            (
                                record["rechecked_at"] - event["published_at"]
                            ).total_seconds()
                            / 60,
                            1,
                        ),
                    }
                    for record in late[:20]
                ],
            }
        )

    per_event.sort(key=lambda item: item["published_at"], reverse=True)

    return {
        "window_minutes": window_minutes,
        "publish_events": len(events),
        "events_with_recheck_records": len(events) - events_without_data,
        "events_without_recheck_records": events_without_data,
        "affected_files": total_affected,
        "on_time_files": total_on_time,
        "late_files": total_affected - total_on_time,
        "overall_ratio": (total_on_time / total_affected) if total_affected else None,
        "per_event": per_event,
    }


async def _collect(
    since: Optional[datetime],
    window_minutes: int,
) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.models.database import AsyncSessionLocal
    from modules.core.db import CatalogFile, FieldMappingTemplate

    async with AsyncSessionLocal() as db:
        templates = list(
            (await db.execute(select(FieldMappingTemplate))).scalars().all()
        )
        files = list((await db.execute(select(CatalogFile))).scalars().all())

    # ── 发布事件 ──────────────────────────────────────────────────────
    events: List[Dict[str, Any]] = []
    for template in templates:
        published_at = _parse_iso(getattr(template, "created_at", None))
        if published_at is None:
            continue
        if since is not None and published_at < since:
            continue
        events.append(
            {
                "template_id": template.id,
                "version": template.version,
                "status": template.status,
                "dimension": _dimension(template),
                "published_at": published_at,
                "template_name": template.template_name,
            }
        )

    # ── 文件侧的重估记录 ─────────────────────────────────────────────
    rechecks: Dict[int, Dict[str, Any]] = {}
    for catalog_file in files:
        meta = catalog_file.file_metadata
        if not isinstance(meta, dict):
            continue
        auto = meta.get("auto_ingest")
        if not isinstance(auto, dict):
            continue
        rechecked_at = _parse_iso(auto.get("last_recheck_at"))
        template_id = auto.get("last_recheck_template_id")
        if rechecked_at is None or template_id is None:
            continue
        try:
            rechecks[int(template_id)] = {
                "file_id": catalog_file.id,
                "rechecked_at": rechecked_at,
                "dimension": _dimension(catalog_file),
            }
        except (TypeError, ValueError):
            continue

    return attribute_rechecks(events, rechecks, window_minutes)


def _print(report: Dict[str, Any]) -> None:
    print("=" * 72)
    print(f"模板发布闭环指标(窗口 = {report['window_minutes']} 分钟内完成重估)")
    print("=" * 72)
    print(f"发布事件总数        : {report['publish_events']}")
    print(f"  其中有重估记录    : {report['events_with_recheck_records']}")
    print(f"  其中无重估记录    : {report['events_without_recheck_records']}")
    print(f"受影响文件(按维度归因): {report['affected_files']}")
    print(f"  窗口内完成重估    : {report['on_time_files']}")
    print(f"  超窗口完成重估    : {report['late_files']}")
    ratio = report["overall_ratio"]
    print(
        f"闭环比例            : {ratio:.1%}"
        if ratio is not None
        else "闭环比例            : (无数据)"
    )
    if report["events_without_recheck_records"]:
        print(
            "\n[注意] 有 "
            f"{report['events_without_recheck_records']} 次发布没有任何重估记录 —— "
            "可能是「这次发布确实没有文件需要重估」,\n"
            "       也可能是「重检没跑到」。埋点从 2026-11-14 起才有, "
            "存量数据一律算「无数据」,\n"
            "       不会被算成达标。"
        )
    late_events = [item for item in report["per_event"] if item["late"]]
    if late_events:
        print("\n-- 超窗口的发布事件 --")
        for item in late_events[:20]:
            print(
                f"  {item['dimension']} v{item['version']} "
                f"发布于 {item['published_at']}: "
                f"{item['on_time']}/{item['affected']} 达标"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="模板发布闭环指标(只读)")
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=15,
        help="达标窗口(分钟, 默认 15 —— 与定时巡检周期一致)",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="只看最近 N 天的发布事件(默认: 全部)",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    since = (
        datetime.now(timezone.utc) - timedelta(days=args.since_days)
        if args.since_days
        else None
    )

    from backend.utils.project_env import load_project_env

    load_project_env(REPO_ROOT)
    report = asyncio.run(_collect(since, args.window_minutes))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
