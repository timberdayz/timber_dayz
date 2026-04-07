#!/usr/bin/env python3
"""
结构一致性检查：验证当前数据库的表、字段与 schema.py（Base.metadata）是否一致。

用于部署后或本地 Docker 化部署测试后，确认「迁移/补表」结果是否达成本地表、字段与预期一致。
用法：
  在项目根目录：python scripts/verify_schema_consistency.py
  或在 backend 容器内：python3 /app/scripts/verify_schema_consistency.py（需复制到镜像）
可选：--columns  同时校验每张表的列名（不校验类型）
可选：--ignore-schema  只校验表名是否存在（任意 schema），不校验 schema 是否与 schema.py 一致（用于迁移已将表迁到 a_class/c_class 但 schema.py 尚未全部更新时）
"""

import sys
from pathlib import Path

# 保证从项目根或容器 /app 均可导入 backend
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)
        except Exception:
            print(msg.encode("ascii", errors="ignore").decode("ascii"), flush=True)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="结构一致性检查：DB 表/列与 schema.py 是否一致")
    parser.add_argument("--columns", action="store_true", help="同时校验每张表的列名")
    parser.add_argument(
        "--ignore-schema",
        action="store_true",
        help="只校验表名是否存在于任意 schema，不校验 schema 一致（迁移已移表时可用）",
    )
    args = parser.parse_args()
    check_columns = args.columns
    ignore_schema = args.ignore_schema

    try:
        from backend.models.database import Base, engine
        from sqlalchemy import inspect
    except Exception as e:
        safe_print(f"[ERROR] 导入失败: {e}")
        return 1

    inspector = inspect(engine)

    # 预期：Base.metadata 中每张表的 (schema, table_name)
    expected = set()
    expected_columns = {}  # (schema, table_name) -> set(column_names)
    for t in Base.metadata.tables.values():
        schema = (t.schema or "public")
        name = t.name
        expected.add((schema, name))
        if check_columns:
            expected_columns[(schema, name)] = set(c.name for c in t.c)

    # 实际：从数据库按 schema 取表
    actual = set()
    try:
        schemas = inspector.get_schema_names()
    except Exception as e:
        safe_print(f"[ERROR] 获取 schema 列表失败: {e}")
        return 1
    # 排除系统 schema，只保留业务相关
    skip_schemas = {"pg_catalog", "information_schema", "pg_toast"}
    for s in schemas:
        if s in skip_schemas:
            continue
        try:
            for name in inspector.get_table_names(schema=s):
                actual.add((s, name))
        except Exception as e:
            safe_print(f"[WARN] 读取 schema {s} 表列表失败: {e}")

    missing = expected - actual
    extra = actual - expected

    if ignore_schema:
        # 只校验「表名」是否在库中存在（任意 schema）
        expected_names = set(n for _s, n in expected)
        actual_names = set(n for _s, n in actual)
        missing_names = expected_names - actual_names
        if missing_names:
            missing = set((s, n) for s, n in expected if n in missing_names)
        else:
            missing = set()
        extra = set()

    # 可选：列名一致性
    column_issues = []
    if check_columns and not missing:
        for (schema, table_name) in expected:
            exp_cols = expected_columns.get((schema, table_name))
            if not exp_cols:
                continue
            try:
                cols = inspector.get_columns(table_name, schema=schema)
                act_cols = set(c["name"] for c in cols)
                miss_cols = exp_cols - act_cols
                if miss_cols:
                    column_issues.append((f"{schema}.{table_name}", "missing_columns", sorted(miss_cols)))
            except Exception as e:
                column_issues.append((f"{schema}.{table_name}", "error", str(e)))

    # 报告
    safe_print("[INFO] 结构一致性检查（预期来源: schema.py / Base.metadata）")
    safe_print(f"  预期表数: {len(expected)}  实际表数: {len(actual)}")
    if missing:
        safe_print(f"[FAIL] 缺失表 ({len(missing)}):")
        for s, n in sorted(missing):
            safe_print(f"  - {s}.{n}")
    if extra:
        safe_print(f"[INFO] 库中多出的表 ({len(extra)}，可能为系统/历史表):")
        for s, n in sorted(extra)[:20]:
            safe_print(f"  - {s}.{n}")
        if len(extra) > 20:
            safe_print(f"  ... 共 {len(extra)} 张")
    if column_issues:
        safe_print("[FAIL] 列不一致:")
        for tbl, kind, detail in column_issues:
            safe_print(f"  - {tbl}: {kind} {detail}")

    if missing or column_issues:
        safe_print("[FAIL] 结构不一致，未达成本地/预期与当前库完全同步。")
        return 1
    safe_print("[OK] 结构一致，表（及可选列）与 schema.py 一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
