#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A 类数据表结构审查脚本

对比「库中实际列」与「schema.py 中模型定义」，输出缺失列、多余列，便于发现
与 sales_targets 类似的「表存在但缺列」问题。

审查范围（业务 A 类，有 API 在用）：
  - sales_targets (SalesTarget)
  - target_breakdown (TargetBreakdown)
  - sales_campaigns (SalesCampaign)
  - sales_campaign_shops (SalesCampaignShop)
  - performance_config (PerformanceConfig)

用法：
  python scripts/check_a_class_tables_schema.py           # 连库审查并打印报告
  python scripts/check_a_class_tables_schema.py --report  # 并写入 docs/A_CLASS_TABLES_AUDIT_REPORT.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _expected_columns(model_cls) -> set[str]:
    return {c.key for c in model_cls.__table__.c}


def _schemas_with_table(conn, table: str) -> list[str]:
    from sqlalchemy import text

    r = conn.execute(
        text("""
        SELECT table_schema FROM information_schema.tables
        WHERE table_name = :t
    """),
        {"t": table},
    )
    return [row[0] for row in r]


def _current_columns(conn, schema: str, table: str) -> set[str]:
    from sqlalchemy import text

    r = conn.execute(
        text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :t
    """),
        {"schema": schema, "t": table},
    )
    return {row[0] for row in r}


def run_audit(engine) -> list[dict]:
    from modules.core.db import (
        SalesTarget,
        TargetBreakdown,
        SalesCampaign,
        SalesCampaignShop,
        PerformanceConfig,
    )

    tables = [
        ("sales_targets", SalesTarget),
        ("target_breakdown", TargetBreakdown),
        ("sales_campaigns", SalesCampaign),
        ("sales_campaign_shops", SalesCampaignShop),
        ("performance_config", PerformanceConfig),
    ]
    results = []
    with engine.connect() as conn:
        for table_name, model_cls in tables:
            expected = _expected_columns(model_cls)
            schemas = _schemas_with_table(conn, table_name)
            for schema in schemas:
                actual = _current_columns(conn, schema, table_name)
                missing = expected - actual
                extra = actual - expected
                results.append(
                    {
                        "table": table_name,
                        "schema": schema,
                        "expected_count": len(expected),
                        "actual_count": len(actual),
                        "missing": sorted(missing),
                        "extra": sorted(extra),
                        "ok": len(missing) == 0,
                    }
                )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="A class tables schema audit")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Write report to docs/A_CLASS_TABLES_AUDIT_REPORT.md",
    )
    args = parser.parse_args()

    from sqlalchemy import create_engine
    from backend.utils.config import get_settings

    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        print("[SKIP] SQLite: audit supports PostgreSQL only.")
        return 0

    engine = create_engine(url, pool_pre_ping=True)
    try:
        results = run_audit(engine)
    except Exception as e:
        print(f"[FAIL] Audit error: {type(e).__name__}: {e}")
        return 1

    lines = []
    lines.append("# A 类数据表结构审查报告")
    lines.append("")
    lines.append("对比「库中实际列」与 `modules/core/db/schema.py` 中模型定义。")
    lines.append("")
    all_ok = True
    for r in results:
        qual = f'{r["schema"]}.{r["table"]}'
        status = "[OK]" if r["ok"] else "[MISSING COLUMNS]"
        if not r["ok"]:
            all_ok = False
        lines.append(f"## {qual} {status}")
        lines.append("")
        lines.append(f"- 期望列数: {r['expected_count']}, 实际列数: {r['actual_count']}")
        if r["missing"]:
            lines.append(f"- **缺失列**: {', '.join(r['missing'])}")
        if r["extra"]:
            lines.append(f"- 多余列（库中有、模型无）: {', '.join(r['extra'])}")
        if r["ok"] and not r["extra"]:
            lines.append("- 与 schema.py 一致。")
        lines.append("")

    report_text = "\n".join(lines)
    print(report_text)

    if args.report:
        out_path = project_root / "docs" / "A_CLASS_TABLES_AUDIT_REPORT.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        print(f"[OK] Report written to {out_path}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
