#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 0.9.1a 迁移对账归档报告

报告内容：
1) 目标表行数
2) 关键字段空值率
3) 抽样记录（每表最多 20 条）
4) 迁移前快照可用性说明
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import text

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal


TARGET_TABLES: Dict[Tuple[str, str], List[List[str]]] = {
    ("a_class", "sales_targets"): [
        ["id"],
        ["platform_code", "平台"],
        ["shop_id", "店铺ID"],
        ["year_month", "年月"],
        ["target_sales", "目标销售额"],
    ],
    ("c_class", "performance_scores"): [
        ["id"],
        ["platform_code"],
        ["shop_id"],
        ["period"],
        ["total_score"],
        ["rank"],
    ],
    ("c_class", "shop_health_scores"): [
        ["id"],
        ["platform_code"],
        ["shop_id"],
        ["health_score"],
    ],
    ("c_class", "shop_alerts"): [
        ["id"],
        ["platform_code"],
        ["shop_id"],
        ["alert_level"],
        ["created_at"],
    ],
}

LEGACY_PUBLIC_TABLES = [
    "sales_targets",
    "performance_scores",
    "shop_health_scores",
    "shop_alerts",
]


def _quote_ident(identifier: str) -> str:
    return f'"{identifier}"'


def _existing_columns(session, schema: str, table: str) -> List[str]:
    rows = session.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = :schema and table_name = :table
            order by ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).fetchall()
    return [r[0] for r in rows]


def _table_exists(session, schema: str, table: str) -> bool:
    row = session.execute(
        text(
            """
            select 1
            from information_schema.tables
            where table_schema = :schema and table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    ).fetchone()
    return row is not None


def _row_count(session, schema: str, table: str) -> int:
    sql = text(f"select count(*) from {_quote_ident(schema)}.{_quote_ident(table)}")
    return int(session.execute(sql).scalar() or 0)


def _null_rates(session, schema: str, table: str, fields: List[str], row_count: int) -> Dict[str, float]:
    if row_count == 0:
        return {f: 0.0 for f in fields}
    rates: Dict[str, float] = {}
    for field in fields:
        sql = text(
            f"select count(*) from {_quote_ident(schema)}.{_quote_ident(table)} "
            f"where {_quote_ident(field)} is null"
        )
        null_count = int(session.execute(sql).scalar() or 0)
        rates[field] = round(null_count / row_count, 4)
    return rates


def _sample_rows(session, schema: str, table: str, fields: List[str], limit: int = 20) -> List[dict]:
    cols = ", ".join(_quote_ident(f) for f in fields)
    order_field = fields[0]
    sql = text(
        f"select {cols} from {_quote_ident(schema)}.{_quote_ident(table)} "
        f"order by {_quote_ident(order_field)} desc limit {limit}"
    )
    rows = session.execute(sql).fetchall()
    return [{fields[i]: row[i] for i in range(len(fields))} for row in rows]


def _pick_fields(columns: List[str], candidates: List[List[str]]) -> List[str]:
    picked: List[str] = []
    for candidate_group in candidates:
        hit = next((name for name in candidate_group if name in columns), None)
        if hit and hit not in picked:
            picked.append(hit)
    return picked


def generate_report() -> Path:
    report_dir = project_root / "reports" / "migration_reconciliation"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"add_performance_income_091a_{ts}.md"

    session = SessionLocal()
    try:
        lines: List[str] = []
        lines.append("# 0.9.1a 迁移对账归档报告")
        lines.append("")
        lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("- 范围: sales_targets/performance_scores/shop_health_scores/shop_alerts")
        lines.append("")

        lines.append("## 1. 迁移前快照可用性")
        lines.append("")
        legacy_exists = []
        for table in LEGACY_PUBLIC_TABLES:
            exists = _table_exists(session, "public", table)
            legacy_exists.append((table, exists))
        lines.append("| 表 | public中是否存在 |")
        lines.append("|---|---|")
        for table, exists in legacy_exists:
            lines.append(f"| `{table}` | {'是' if exists else '否'} |")
        lines.append("")
        lines.append(
            "说明：若 public 旧表均不存在，表示迁移后状态正确；但无法在当前环境直接复原“迁移前”行数，"
            "需结合执行迁移前导出的备份文件做严格前后对账。"
        )
        lines.append("")

        lines.append("## 2. 迁移后对账（行数/空值率/抽样）")
        lines.append("")
        for (schema, table), candidate_fields in TARGET_TABLES.items():
            lines.append(f"### {schema}.{table}")
            if not _table_exists(session, schema, table):
                lines.append("")
                lines.append("- 状态: 表不存在")
                lines.append("")
                continue
            columns = _existing_columns(session, schema, table)
            fields = _pick_fields(columns, candidate_fields)
            if not fields:
                fields = columns[: min(6, len(columns))]
            count = _row_count(session, schema, table)
            null_rates = _null_rates(session, schema, table, fields, count)
            sample = _sample_rows(session, schema, table, fields, limit=20)

            lines.append("")
            lines.append(f"- 行数: `{count}`")
            lines.append("- 关键字段空值率:")
            for field in fields:
                lines.append(f"  - `{field}`: `{null_rates[field]}`")
            lines.append("- 抽样（最多 20 条）:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(sample, ensure_ascii=False, default=str, indent=2))
            lines.append("```")
            lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
    finally:
        session.close()


def main() -> int:
    path = generate_report()
    print(f"[OK] report generated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
