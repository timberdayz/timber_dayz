#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案二：不依赖 Alembic，直接对 sales_targets 补齐缺失列

当 alembic_version 指向已归档的 20260111_complete_missing 导致无法执行
20260125_fix_sales_targets_columns 时，可在本机运行此脚本，直接执行等价的
ALTER TABLE，使 sales_targets 与 schema.py 中 SalesTarget 一致，解决目标管理 500。

用法（在项目根目录或任意处可找到 backend 时）：
  python scripts/fix_sales_targets_columns_standalone.py

依赖：与后端相同数据库（.env 中 DATABASE_URL 或默认 PostgreSQL）。
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


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


def main() -> int:
    from sqlalchemy import create_engine, text

    from backend.utils.config import get_settings

    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        print("[SKIP] SQLite not supported (sales_targets fix is for PostgreSQL).")
        return 0

    engine = create_engine(url, pool_pre_ping=True)
    schemas = []
    with engine.connect() as conn:
        schemas = _schemas_with_table(conn, "sales_targets")

    if not schemas:
        print("[OK] No sales_targets table found in any schema, nothing to do.")
        return 0

    updated = 0
    with engine.connect() as conn:
        for schema in schemas:
            cols = _current_columns(conn, schema, "sales_targets")
            if not cols:
                continue
            if "target_name" in cols:
                print(f"[OK] {schema}.sales_targets already has target_name, skip.")
                continue
            qual = f'"{schema}".sales_targets' if schema != "public" else "sales_targets"
            add_sql = []
            if "target_name" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN target_name VARCHAR(200) NOT NULL DEFAULT ''"
                )
            if "target_type" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN target_type VARCHAR(32) NOT NULL DEFAULT 'shop'"
                )
            if "period_start" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN period_start DATE NOT NULL DEFAULT '1970-01-01'"
                )
            if "period_end" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN period_end DATE NOT NULL DEFAULT '1970-01-01'"
                )
            if "target_amount" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN target_amount NUMERIC NOT NULL DEFAULT 0"
                )
            if "target_quantity" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN target_quantity INTEGER NOT NULL DEFAULT 0"
                )
            if "achieved_amount" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN achieved_amount NUMERIC NOT NULL DEFAULT 0"
                )
            if "achieved_quantity" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN achieved_quantity INTEGER NOT NULL DEFAULT 0"
                )
            if "achievement_rate" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN achievement_rate NUMERIC NOT NULL DEFAULT 0"
                )
            if "status" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'"
                )
            if "description" not in cols:
                add_sql.append(f"ALTER TABLE {qual} ADD COLUMN description TEXT")
            if "created_by" not in cols:
                add_sql.append(f"ALTER TABLE {qual} ADD COLUMN created_by VARCHAR(64)")
            if "created_at" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "updated_at" not in cols:
                add_sql.append(
                    f"ALTER TABLE {qual} ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            for stmt in add_sql:
                conn.execute(text(stmt))
            conn.commit()
            updated += 1
            print(f"[OK] {schema}.sales_targets: added {len(add_sql)} column(s).")

    if updated:
        print(f"[DONE] Updated {updated} schema(s). Restart backend and retry targets API.")
    else:
        print("[DONE] No schema needed changes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        sys.exit(1)
