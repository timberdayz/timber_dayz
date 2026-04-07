#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 schema.py（Base.metadata）对当前数据库补列：仅对已存在的表执行 ADD COLUMN（缺失列），不删列、不改类型。

用于部署时「迁移失败且所有表都存在」的兜底：云服务器旧 schema 缺列时，一次补齐后重试迁移。
用法：
  在项目根目录：python scripts/sync_schema_columns.py
  或在 backend 容器内：python3 /app/scripts/sync_schema_columns.py
可选：--dry-run  只打印将要执行的 ALTER，不执行
"""

import sys
from pathlib import Path

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
    parser = argparse.ArgumentParser(description="按 schema.py 对已存在的表补列（ADD COLUMN）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不执行")
    args = parser.parse_args()
    dry_run = args.dry_run

    try:
        from backend.models.database import Base, engine
        from sqlalchemy import inspect, text
    except Exception as e:
        safe_print(f"[ERROR] 导入失败: {e}")
        return 1

    inspector = inspect(engine)
    skip_schemas = {"pg_catalog", "information_schema", "pg_toast"}
    # 已存在的 (schema, table_name) -> set(column_name)
    existing_tables_columns = {}
    try:
        for s in inspector.get_schema_names():
            if s in skip_schemas:
                continue
            for tname in inspector.get_table_names(schema=s):
                key = (s, tname)
                cols = inspector.get_columns(tname, schema=s)
                existing_tables_columns[key] = {c["name"] for c in cols}
    except Exception as e:
        safe_print(f"[ERROR] 读取库表失败: {e}")
        return 1

    added = 0
    errors = []

    for table in Base.metadata.tables.values():
        schema = table.schema or "public"
        tname = table.name
        key = (schema, tname)
        if key not in existing_tables_columns:
            continue
        existing_cols = existing_tables_columns[key]
        expected_cols = {c.name for c in table.c}
        missing = expected_cols - existing_cols
        if not missing:
            continue
        qual = f'"{schema}"."{tname}"'
        for col in table.c:
            if col.name not in missing:
                continue
            try:
                type_str = col.type.compile(dialect=engine.dialect)
            except Exception as e:
                errors.append((qual, col.name, str(e)))
                continue
            # 可空或暂无默认：先加 NULL；有 server_default 的用 DEFAULT
            if col.nullable:
                suffix = " NULL"
            elif col.server_default is not None:
                # 简单处理：有默认则用 DEFAULT，否则加 NULL 并告警
                try:
                    default_str = str(col.server_default.arg) if hasattr(col.server_default, "arg") else str(col.server_default)
                    if default_str.upper() in ("NOW()", "CURRENT_TIMESTAMP", "LOCALTIMESTAMP"):
                        suffix = " DEFAULT CURRENT_TIMESTAMP"
                    else:
                        suffix = " NULL"
                        safe_print(f"[WARN] {qual}.{col.name} NOT NULL 有 server_default 暂未生成 DEFAULT，先加 NULL")
                except Exception:
                    suffix = " NULL"
            else:
                suffix = " NULL"
                safe_print(f"[WARN] {qual}.{col.name} 为 NOT NULL 无默认值，先加 NULL，请后续手动补默认或数据")
            col_quoted = f'"{col.name}"'
            stmt = f'ALTER TABLE {qual} ADD COLUMN IF NOT EXISTS {col_quoted} {type_str}{suffix}'
            if dry_run:
                safe_print(f"[DRY-RUN] {stmt}")
            else:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(stmt))
                        conn.commit()
                    safe_print(f"[OK] {qual} ADD COLUMN {col.name}")
                except Exception as e:
                    errors.append((qual, col.name, str(e)))
            added += 1

    if errors:
        safe_print("[FAIL] 部分列添加失败:")
        for qual, col, err in errors:
            safe_print(f"  - {qual}.{col}: {err}")
        return 1
    if added == 0:
        safe_print("[OK] 无缺失列，无需补列")
    else:
        safe_print(f"[OK] 补列完成，共 {added} 列")
    return 0


if __name__ == "__main__":
    sys.exit(main())
