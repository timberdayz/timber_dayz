#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集相关表字段检查与修复脚本

检查 collection_tasks / collection_configs / collection_task_logs 是否缺少 ORM 所需字段，
若缺少则执行 ALTER TABLE 添加（仅 PostgreSQL，幂等）。

用法:
  python scripts/check_and_fix_collection_tables.py          # 仅检查并打印报告
  python scripts/check_and_fix_collection_tables.py --fix   # 检查并自动添加缺失列

说明:
  - 若采集模块报「内部服务器错误」，多为 collection_tasks 表缺少 started_at/completed_at。
  - 请先执行: alembic upgrade head
  - 若迁移未生效或迁移失败，可执行本脚本加 --fix 直接补列，然后重启后端。

依赖: 项目根目录 .env 中 DATABASE_URL 或 backend 可导入 get_settings。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 确保能加载 backend
os.chdir(ROOT)


def get_db_url() -> str:
    try:
        from backend.utils.config import get_settings
        return get_settings().DATABASE_URL
    except Exception:
        pass
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("未设置 DATABASE_URL，请在 .env 中配置或确保 backend 可导入")
    return url


# 与 modules/core/db/schema.py 中 CollectionTask 必须一致的列（缺一会导致 ORM 查询报错）
COLLECTION_TASKS_REQUIRED_COLUMNS = [
    "id", "task_id", "platform", "account", "status", "config_id",
    "progress", "current_step", "files_collected", "trigger_type",
    "data_domains", "sub_domains", "granularity", "date_range",
    "total_domains", "completed_domains", "failed_domains", "current_domain",
    "error_message", "error_screenshot_path", "duration_seconds",
    "started_at",   # 常因迁移未执行而缺失
    "completed_at", # 常因迁移未执行而缺失
    "retry_count", "parent_task_id", "verification_type", "verification_screenshot",
    "debug_mode", "version", "created_at", "updated_at",
]

# 需要添加的列及其 SQL 类型（仅列出可能缺失的，用于 --fix）
COLLECTION_TASKS_ADD_COLUMNS = [
    ("started_at", "TIMESTAMP"),
    ("completed_at", "TIMESTAMP"),
]


def column_exists(conn, table: str, column: str, schema: str = "public") -> bool:
    from sqlalchemy import text
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :t AND column_name = :col
    """), {"schema": schema, "t": table, "col": column})
    return r.fetchone() is not None


def table_exists(conn, table: str, schema: str = "public") -> bool:
    from sqlalchemy import text
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :t
    """), {"schema": schema, "t": table})
    return r.fetchone() is not None


def get_current_columns(conn, table: str, schema: str = "public") -> list[str]:
    from sqlalchemy import text
    r = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :t
        ORDER BY ordinal_position
    """), {"schema": schema, "t": table})
    return [row[0] for row in r.fetchall()]


def run_check_and_fix(fix: bool = False) -> None:
    from sqlalchemy import create_engine, text

    url = get_db_url()
    if not url.startswith("postgresql"):
        print("[SKIP] 仅支持 PostgreSQL，当前 DATABASE_URL 非 PostgreSQL")
        return

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        schema = "public"
        # 1) collection_tasks
        if not table_exists(conn, "collection_tasks", schema):
            print("[WARN] 表 collection_tasks 不存在，请先执行 alembic upgrade head")
            return
        current = set(get_current_columns(conn, "collection_tasks", schema))
        required = set(COLLECTION_TASKS_REQUIRED_COLUMNS)
        missing = required - current
        if missing:
            print("[CHECK] collection_tasks 缺失列:", sorted(missing))
            if fix:
                for col, typ in COLLECTION_TASKS_ADD_COLUMNS:
                    if col in missing:
                        conn.execute(text(
                            f'ALTER TABLE {schema}.collection_tasks ADD COLUMN IF NOT EXISTS "{col}" {typ}'
                        ))
                        print(f"  [FIX] 已添加 collection_tasks.{col}")
        else:
            print("[OK] collection_tasks 所需列齐全")

        # 2) collection_configs 仅做存在性检查（通常不缺列）
        if table_exists(conn, "collection_configs", schema):
            cols = get_current_columns(conn, "collection_configs", schema)
            for c in ("name", "platform", "account_ids", "data_domains", "is_active"):
                if c not in cols:
                    print(f"[WARN] collection_configs 缺失列: {c}")
        else:
            print("[WARN] 表 collection_configs 不存在")

        # 3) collection_task_logs
        if table_exists(conn, "collection_task_logs", schema):
            cols = set(get_current_columns(conn, "collection_task_logs", schema))
            for c in ("id", "task_id", "level", "message", "details", "timestamp"):
                if c not in cols:
                    print(f"[WARN] collection_task_logs 缺失列: {c}")
        else:
            print("[WARN] 表 collection_task_logs 不存在")

    print("完成。若已执行 --fix，请重启后端再访问采集模块。")


def main():
    fix = "--fix" in sys.argv
    if fix:
        print("将检查并尝试添加缺失列...")
    else:
        print("仅检查（要自动修复请加 --fix）...")
    run_check_and_fix(fix=fix)


if __name__ == "__main__":
    main()
