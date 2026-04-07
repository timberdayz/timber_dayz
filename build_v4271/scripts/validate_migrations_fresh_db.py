#!/usr/bin/env python3
"""
临时库迁移门禁脚本：在全新临时 Postgres 上执行 alembic upgrade heads，与 CI 的 Validate Database Migrations 等价。

用途：发布前在本地复现「从零跑全量迁移」的门禁，不触碰开发库或现有 compose 的 Postgres 卷。
用法：python scripts/validate_migrations_fresh_db.py [--port 5433]
可选参数：--port PORT  临时 Postgres 映射到本机的端口，默认 5433（避免与开发库 5432 冲突）
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5433
PG_USER = "migration_test_user"
PG_PASSWORD = "migration_test_pass"
PG_DB = "migration_test_db"
IMAGE = "postgres:15"
DATA_SYNC_CRITICAL_COLUMNS: dict[str, set[str]] = {
    "core.data_quarantine": {"catalog_file_id"},
    "core.staging_orders": {"file_id"},
    "core.staging_product_metrics": {"file_id"},
    "core.staging_inventory": {"file_id"},
}


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)
        except Exception:
            print(msg.encode("ascii", errors="ignore").decode("ascii"), flush=True)


def run(cmd: list, cwd: Path = None, env: dict = None, timeout: int = 120) -> tuple[int, str]:
    """Run command, return (returncode, combined_output)."""
    cwd = cwd or PROJECT_ROOT
    env = env or os.environ
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            env={**os.environ, **env} if isinstance(env, dict) else env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return (r.returncode, out)
    except subprocess.TimeoutExpired:
        return (-1, "Command timed out")
    except FileNotFoundError:
        return (-1, f"Command not found: {cmd[0]}")


def find_missing_data_sync_critical_columns(conn_inspector) -> list[str]:
    missing_columns: list[str] = []

    for qualified_table, required_columns in DATA_SYNC_CRITICAL_COLUMNS.items():
        schema_name, table_name = qualified_table.split(".", 1)
        actual_columns = {
            column["name"]
            for column in conn_inspector.get_columns(table_name, schema=schema_name)
        }
        for column_name in sorted(required_columns - actual_columns):
            missing_columns.append(f"{qualified_table}.{column_name}")

    return sorted(missing_columns)


def verify_data_sync_critical_columns(database_url: str) -> list[str]:
    engine = create_engine(database_url)
    try:
        conn_inspector = inspect(engine)
        return find_missing_data_sync_critical_columns(conn_inspector)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="临时库迁移门禁：在全新临时 Postgres 上跑 alembic upgrade heads")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"临时 Postgres 端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()
    port = args.port

    safe_print(f"[INFO] 启动临时 Postgres 容器（端口 {port}）...")
    # --rm so container is removed when stopped; -d detached
    cmd = [
        "docker", "run", "--rm", "-d",
        "-e", f"POSTGRES_USER={PG_USER}",
        "-e", f"POSTGRES_PASSWORD={PG_PASSWORD}",
        "-e", f"POSTGRES_DB={PG_DB}",
        "-p", f"{port}:5432",
        IMAGE,
    ]
    code, out = run(cmd, timeout=30)
    if code != 0:
        safe_print("[FAIL] 启动临时 Postgres 失败")
        safe_print(out)
        return 1
    container_id = (out.strip().split("\n")[0] or "").strip()
    if not container_id:
        safe_print("[FAIL] 无法获取容器 ID")
        return 1

    try:
        safe_print("[INFO] 等待 Postgres 就绪...")
        for i in range(60):
            code, _ = run(["docker", "exec", container_id, "pg_isready", "-U", PG_USER, "-d", PG_DB], timeout=5)
            if code == 0:
                break
            time.sleep(1)
        else:
            safe_print("[FAIL] Postgres 就绪超时")
            return 1
        safe_print("[OK] Postgres 就绪")

        database_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@127.0.0.1:{port}/{PG_DB}"
        safe_print("[INFO] 执行 alembic upgrade heads...")
        code, out = run(
            [sys.executable, "-m", "alembic", "upgrade", "heads"],
            cwd=PROJECT_ROOT,
            env={"DATABASE_URL": database_url},
            timeout=300,
        )
        if code != 0:
            safe_print("[FAIL] 迁移失败")
            safe_print(out[-3000:] if len(out) > 3000 else out)
            return 1
        safe_print("[OK] 迁移成功")
        missing_columns = verify_data_sync_critical_columns(database_url)
        if missing_columns:
            safe_print("[FAIL] 迁移后数据同步关键列缺失")
            for missing_column in missing_columns:
                safe_print(f"  - {missing_column}")
            return 1
        safe_print("[OK] 数据同步关键列校验通过")
        return 0
    finally:
        safe_print("[INFO] 停止并删除临时容器...")
        run(["docker", "stop", "-t", "3", container_id], timeout=10)
        safe_print("[OK] 临时容器已移除")

    return 0


if __name__ == "__main__":
    sys.exit(main())
