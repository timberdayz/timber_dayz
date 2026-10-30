#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Hash 数据健康度巡检（**只读**）。

为什么需要它
------------
``data_hash`` 唯一索引只能保证「**同一个 hash** 不重复」，
但保证不了「**同一笔业务** 只有一行」。

当模板把 ``订单状态`` 这类**度量字段**写进 ``deduplication_fields`` 时，
业务状态一变 → hash 变 → 库里多出一行"同一笔订单"。
这种重复不会触发任何报错，只会悄悄把数据越攒越多、报表越算越歪。

这个脚本定期回答一个问题
------------------------
**同一业务键（business key）在库里出现了几行？**

业务键按数据域定义（见 ``BUSINESS_KEYS``）：

- ``orders``   → 平台 + 店铺 + 统计日期 + 订单号
- ``products`` → 平台 + 店铺 + 统计日期 + 商品 ID
- ``services`` → 平台 + 店铺 + 子域 + 统计日期 + 服务日期

同一个业务键出现多行 ⇒ 口径太粗（度量字段混进了身份键）或周期键缺失。

安全性
------
* **只读**：全程不写库；
* 默认退出码 0（只报告）；``--strict`` 时有重复返回 1；
* ``--baseline`` 与上一次报告对比，输出**增量**（新增了多少重复业务键），
  而不是只看存量 —— 存量是历史欠账，增量才是"正在变坏"的信号。

用法
----
    python scripts/audit_data_hash_health.py
    python scripts/audit_data_hash_health.py --json logs/data_hash_health.json
    python scripts/audit_data_hash_health.py --baseline logs/data_hash_health_prev.json
    python scripts/audit_data_hash_health.py --strict
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from backend.models.database import AsyncSessionLocal  # noqa: E402

# 各数据域的"业务键"定义：同一笔业务在同一统计周期内应当只有一行。
#
# ⚠️ 这是**业务口径**，不是 hash 口径：hash 还会带上 system_scope 字段
# （platform_code / shop_id / data_domain / granularity / sub_domain）
# 与自动日期字段。这里只挑"能唯一标识一笔业务"的那些列。
BUSINESS_KEYS: Dict[str, Dict[str, Any]] = {
    "orders": {
        "view": "semantic.fact_orders_atomic",
        "columns": ["platform_code", "shop_id", "metric_date", "order_id"],
    },
    "products": {
        "view": "semantic.fact_products_atomic",
        "columns": ["platform_code", "shop_id", "metric_date", "product_id"],
    },
    "services": {
        "view": "semantic.fact_services_atomic",
        "columns": [
            "platform_code",
            "shop_id",
            "sub_domain",
            "metric_date",
            "service_date",
        ],
    },
}

# 单个域最多保留多少个重复键指纹（够定位问题，又不至于让报告文件爆掉）。
MAX_FINGERPRINTS = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Data Hash 数据健康度巡检（只读）")
    parser.add_argument("--json", dest="json_path", help="把报告写到该 JSON 文件")
    parser.add_argument("--baseline", help="与上一次报告 JSON 对比，输出增量")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="有重复业务键时返回退出码 1（CI 用）",
    )
    parser.add_argument(
        "--fail-on-new",
        action="store_true",
        help="只对**相对基线新增**的重复业务键返回退出码 1（守住增量）",
    )
    parser.add_argument(
        "--max-print",
        type=int,
        default=10,
        help="每个域最多打印多少条重复样例（默认 10）",
    )
    return parser.parse_args()


def _fingerprint(values: List[Any]) -> str:
    """业务键的稳定指纹（用于跨次对比"是不是同一批重复"）。"""
    raw = "|".join("" if value is None else str(value) for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def _view_columns(session: Any, view: str) -> List[str]:
    schema, _, name = view.partition(".")
    rows = (
        await session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :name
                ORDER BY ordinal_position
                """
            ),
            {"schema": schema, "name": name},
        )
    ).fetchall()
    return [row[0] for row in rows]


async def audit_domain(
    session: Any, domain: str, spec: Dict[str, Any]
) -> Dict[str, Any]:
    """统计单个数据域的"同一业务键多行"情况。"""
    view = spec["view"]
    available = await _view_columns(session, view)
    if not available:
        return {
            "domain": domain,
            "view": view,
            "available": False,
            "reason": f"视图 {view} 不存在",
            "total_rows": 0,
            "duplicate_groups": 0,
            "extra_rows": 0,
            "fingerprints": [],
            "samples": [],
        }

    columns = [column for column in spec["columns"] if column in available]
    missing = [column for column in spec["columns"] if column not in available]
    if not columns:
        return {
            "domain": domain,
            "view": view,
            "available": False,
            "reason": f"视图 {view} 缺少业务键列：{missing}",
            "total_rows": 0,
            "duplicate_groups": 0,
            "extra_rows": 0,
            "fingerprints": [],
            "samples": [],
        }

    key_expr = ", ".join(f'"{column}"' for column in columns)
    where_clause = " AND ".join(f'"{column}" IS NOT NULL' for column in columns)

    total_rows = (
        await session.execute(text(f"SELECT COUNT(*) FROM {view}"))
    ).scalar() or 0

    dup_sql = f"""
        SELECT {key_expr}, COUNT(*) AS row_count
        FROM {view}
        WHERE {where_clause}
        GROUP BY {key_expr}
        HAVING COUNT(*) > 1
    """
    dup_rows = (await session.execute(text(dup_sql))).fetchall()

    duplicate_groups = len(dup_rows)
    extra_rows = sum(int(row[-1]) - 1 for row in dup_rows)
    fingerprints = [_fingerprint(list(row[:-1])) for row in dup_rows]
    samples = [
        {column: _jsonable(value) for column, value in zip(columns, row[:-1])}
        | {"row_count": int(row[-1])}
        for row in dup_rows
    ]

    return {
        "domain": domain,
        "view": view,
        "available": True,
        "business_key_columns": columns,
        "missing_key_columns": missing,
        "total_rows": int(total_rows),
        "duplicate_groups": duplicate_groups,
        "extra_rows": extra_rows,
        "fingerprints": fingerprints[:MAX_FINGERPRINTS],
        "fingerprint_truncated": len(fingerprints) > MAX_FINGERPRINTS,
        "samples": samples[:MAX_FINGERPRINTS],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def build_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domains": results,
        "total_duplicate_groups": sum(
            int(item.get("duplicate_groups") or 0) for item in results
        ),
        "total_extra_rows": sum(int(item.get("extra_rows") or 0) for item in results),
    }


def compare_with_baseline(report: Dict[str, Any], baseline_path: str) -> Dict[str, Any]:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    base_by_domain = {
        item.get("domain"): item for item in baseline.get("domains") or []
    }
    cur_by_domain = {item.get("domain"): item for item in report.get("domains") or []}

    diffs: Dict[str, Any] = {}
    total_new = 0
    for domain, current in cur_by_domain.items():
        base = base_by_domain.get(domain) or {}
        base_fps = set(base.get("fingerprints") or [])
        cur_fps = set(current.get("fingerprints") or [])
        new_fps = cur_fps - base_fps
        fixed_fps = base_fps - cur_fps
        total_new += len(new_fps)
        diffs[domain] = {
            "baseline_duplicate_groups": int(base.get("duplicate_groups") or 0),
            "current_duplicate_groups": int(current.get("duplicate_groups") or 0),
            "new_duplicate_keys": len(new_fps),
            "fixed_duplicate_keys": len(fixed_fps),
            "new_fingerprints": sorted(new_fps)[:50],
        }
    return {
        "baseline_generated_at": baseline.get("generated_at"),
        "baseline_total_duplicate_groups": int(
            baseline.get("total_duplicate_groups") or 0
        ),
        "current_total_duplicate_groups": int(
            report.get("total_duplicate_groups") or 0
        ),
        "new_duplicate_keys_total": total_new,
        "by_domain": diffs,
    }


def print_report(report: Dict[str, Any], max_print: int) -> None:
    print("=" * 90)
    print("Data Hash 数据健康度巡检（只读）")
    print("=" * 90)
    for item in report.get("domains", []):
        if not item.get("available"):
            print(f"\n  [{item['domain']}] {item['view']} → 跳过：{item.get('reason')}")
            continue
        print(
            f"\n  [{item['domain']}] {item['view']}"
            f"  业务键 = {' + '.join(item.get('business_key_columns') or [])}"
        )
        print(f"        总行数: {item['total_rows']}")
        print(
            f"        重复业务键: {item['duplicate_groups']} 组"
            f"（多出来的行数: {item['extra_rows']}）"
        )
        for sample in (item.get("samples") or [])[:max_print]:
            key_text = ", ".join(
                f"{key}={value}" for key, value in sample.items() if key != "row_count"
            )
            print(f"          - {key_text}  ×{sample.get('row_count')}")
        if len(item.get("samples") or []) > max_print:
            print(f"          ... 其余 {len(item['samples']) - max_print} 组未打印")
    print("-" * 90)
    print(
        f"  合计: 重复业务键 {report['total_duplicate_groups']} 组，"
        f"多出来的行 {report['total_extra_rows']} 行"
    )


async def main() -> int:
    args = parse_args()
    results: List[Dict[str, Any]] = []
    async with AsyncSessionLocal() as session:
        for domain, spec in BUSINESS_KEYS.items():
            results.append(await audit_domain(session, domain, spec))

    report = build_report(results)
    print_report(report, args.max_print)

    diff: Optional[Dict[str, Any]] = None
    if args.baseline:
        diff = compare_with_baseline(report, args.baseline)
        report["baseline_diff"] = diff
        print("-" * 90)
        print("  与基线对比（看增量，不看存量）:")
        print(f"    基线时间: {diff['baseline_generated_at']}")
        print(
            f"    重复业务键: {diff['baseline_total_duplicate_groups']} → "
            f"{diff['current_total_duplicate_groups']}"
        )
        print(f"    新增重复业务键: {diff['new_duplicate_keys_total']}")
        for domain, item in diff["by_domain"].items():
            print(
                f"      - {domain}: 新增 {item['new_duplicate_keys']} 组 / "
                f"修复 {item['fixed_duplicate_keys']} 组"
            )

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n[INFO] 报告已写入: {out}")

    if args.fail_on_new:
        if not args.baseline:
            print("\n[ERROR] --fail-on-new 需要配合 --baseline 使用")
            return 2
        new_count = diff["new_duplicate_keys_total"] if diff else 0
        if new_count:
            print(f"\n[ERROR] 相对基线新增 {new_count} 组重复业务键")
            return 1
        return 0

    if args.strict and report["total_duplicate_groups"]:
        print(
            f"\n[ERROR] 发现 {report['total_duplicate_groups']} 组重复业务键"
            "（--strict 模式返回失败）"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
