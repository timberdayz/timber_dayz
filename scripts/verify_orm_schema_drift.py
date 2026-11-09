#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁：ORM 声明的列必须真实存在于数据库（结构漂移体检）。

背景（SSOT）
------------
ORM(``modules/core/db/schema.py``)与真实库之间存在**列结构漂移**时，
代码一用到那列就抛 ``UndefinedColumnError``，现场表现为接口 500
（例如 ``/api/hr/attendance`` 报 ``attendance_records.employee_code`` 不存在）。

漂移之所以能长期存在，是因为**没有任何环节校验 ORM 与库是否一致**：
迁移只管建表，ORM 只管声明，谁也不看对方。

本门禁把「ORM 与库必须一致」变成可执行的体检：

* ORM 声明了、库里没有 ⇒ **失败**（代码一用就 500）
* 库里多出、ORM 没有 ⇒ 仅提示（不影响运行，多半是历史遗留列）

用法
----
    python scripts/verify_orm_schema_drift.py
    python scripts/verify_orm_schema_drift.py --json
    python scripts/verify_orm_schema_drift.py --allow-missing-table   # 允许整表缺失

没有 ``DATABASE_URL`` 时直接退出码 2（**不静默跳过**），
避免「体检没跑却看起来通过了」。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_metadata():
    sys.path.insert(0, str(ROOT))
    from modules.core.db.schema import Base  # noqa: PLC0415

    return Base.metadata


def _db_columns(inspector, schema: str, table: str) -> set[str] | None:
    try:
        return {c["name"] for c in inspector.get_columns(table, schema=schema)}
    except Exception:  # noqa: BLE001
        return None


def _find_table_columns(inspector, schema: str | None, bare: str) -> set[str] | None:
    """按 schema 优先级找表：ORM 声明的 schema → public → 其它 schema。"""
    candidates = []
    if schema:
        candidates.append(schema)
    default = inspector.default_schema_name
    if default not in candidates:
        candidates.append(default)
    for sch in inspector.get_schema_names():
        if sch not in candidates:
            candidates.append(sch)
    for sch in candidates:
        cols = _db_columns(inspector, sch, bare)
        if cols is not None:
            return cols
    return None


def check(database_url: str, allow_missing_table: bool = False) -> dict:
    """返回体检结果字典。"""
    from sqlalchemy import create_engine, inspect  # noqa: PLC0415

    engine = create_engine(database_url)
    inspector = inspect(engine)
    metadata = _load_metadata()

    missing_columns: list[dict] = []
    missing_tables: list[str] = []
    extra_columns: list[dict] = []

    for table_name, table in sorted(metadata.tables.items()):
        # schema 以 ORM 声明为准（__table_args__ 里的 {"schema": "core"}）；
        # 未声明时按表名在所有 schema 中查找。
        schema = table.schema
        bare = table_name.split(".", 1)[1] if "." in table_name else table_name

        db_cols = _find_table_columns(inspector, schema, bare)
        if db_cols is None:
            missing_tables.append(table_name)
            continue

        orm_cols = {c.name for c in table.columns}
        for col in sorted(orm_cols - db_cols):
            missing_columns.append({"table": table_name, "column": col})
        for col in sorted(db_cols - orm_cols):
            extra_columns.append({"table": table_name, "column": col})

    engine.dispose()
    return {
        "missing_tables": sorted(missing_tables),
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "tables_checked": len(metadata.tables),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ORM ↔ 数据库 结构漂移体检")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="数据库连接串，默认取环境变量 DATABASE_URL",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument(
        "--allow-missing-table",
        action="store_true",
        help="整表在库中缺失时不判失败（默认判失败）",
    )
    args = parser.parse_args()

    if not args.database_url:
        print(
            "[orm-drift-gate] 未提供 DATABASE_URL，无法体检（退出码 2，不静默跳过）",
            file=sys.stderr,
        )
        return 2

    result = check(args.database_url, allow_missing_table=args.allow_missing_table)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[orm-drift-gate] 已检查 {result['tables_checked']} 张表")
        if result["missing_columns"]:
            print(
                f"[orm-drift-gate] 发现 {len(result['missing_columns'])} 处"
                "「ORM 有、库里没有」的列（代码一用就 500）："
            )
            for item in result["missing_columns"]:
                print(f"  - {item['table']}.{item['column']}")
        if result["missing_tables"]:
            print(f"[orm-drift-gate] 库中缺失的表：{result['missing_tables']}")
        if result["extra_columns"]:
            print(
                f"[orm-drift-gate] 提示：{len(result['extra_columns'])} 处"
                "「库有、ORM 没有」的列（不影响运行，历史遗留）"
            )

    if result["missing_columns"]:
        return 1
    if result["missing_tables"] and not args.allow_missing_table:
        return 1
    print("[orm-drift-gate] OK：ORM 声明的列在数据库中都存在")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
