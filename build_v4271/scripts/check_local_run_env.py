#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
本地启动环境检查（local_run.py 用）

检查 .env 中的 DATABASE_URL 与 Postgres 是否满足后端启动要求。
用法: python scripts/check_local_run_env.py
"""

import os
import sys
from pathlib import Path
from typing import Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

_env_file = project_root / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        try:
            load_dotenv(_env_file, encoding="utf-8")
        except TypeError:
            load_dotenv(_env_file)
    except ImportError:
        pass


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)


def parse_pg_url(url: str) -> dict:
    """从 DATABASE_URL 解析 host, port, user, password, dbname"""
    if not url or not url.startswith("postgresql"):
        return {}
    # postgresql://user:pass@host:port/dbname 或 postgresql://user:pass@host/dbname
    from urllib.parse import urlparse
    p = urlparse(url)
    host = p.hostname or "localhost"
    port = p.port if p.port is not None else 5432
    user = p.username or "postgres"
    password = p.password or ""
    dbname = (p.path or "").strip("/") or "postgres"
    return {"host": host, "port": port, "user": user, "password": password, "dbname": dbname}


def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    """检查 host:port 是否有 TCP 监听"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def check_postgres_connect(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """尝试用 SQLAlchemy 连接 Postgres，返回 (成功?, 错误信息)"""
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(url, connect_args={"connect_timeout": timeout})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True, ""
    except Exception as e:
        return False, str(e)


def main() -> None:
    safe_print("=" * 60)
    safe_print("本地启动环境检查 (local_run.py)")
    safe_print("=" * 60)

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        safe_print("[FAIL] .env 中未设置 DATABASE_URL")
        safe_print("  建议: 在项目根 .env 中添加 DATABASE_URL=postgresql://...")
        sys.exit(1)

    if not url.startswith("postgresql"):
        safe_print(f"[WARN] 当前 DATABASE_URL 不是 PostgreSQL: {url[:50]}...")
        safe_print("  后端默认需要 PostgreSQL，请改为 postgresql://...")
        sys.exit(1)

    info = parse_pg_url(url)
    if not info:
        safe_print("[FAIL] 无法解析 DATABASE_URL")
        sys.exit(1)

    safe_print("\n[配置] 当前 .env 中的数据库配置:")
    safe_print(f"  主机: {info['host']}")
    safe_print(f"  端口: {info['port']}")
    safe_print(f"  用户: {info['user']}")
    safe_print(f"  数据库: {info['dbname']}")
    safe_print("  密码: ****")

    # 1. TCP 是否可达
    safe_print("\n[检查] TCP 连接 ...")
    if not check_tcp(info["host"], info["port"]):
        safe_print(f"  [FAIL] 无法连接到 {info['host']}:{info['port']}")
        if info["port"] == 15432:
            safe_print("  说明: 15432 为 Docker 映射端口，需先启动 Docker 中的 Postgres:")
            safe_print("        docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d postgres")
            safe_print("  若使用本机安装的 PostgreSQL（通常为 5432），请将 .env 中改为:")
            safe_print("        POSTGRES_PORT=5432")
            safe_print("        DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp")
            safe_print("  并在本机 Postgres 中创建用户 erp_user、数据库 xihong_erp。")
        else:
            safe_print("  请确认 PostgreSQL 已启动，且主机/端口正确。")
        sys.exit(1)
    safe_print("  [OK] 端口可达")

    # 2. 数据库连接与认证
    safe_print("\n[检查] 数据库连接与认证 ...")
    ok, err = check_postgres_connect(url)
    if not ok:
        safe_print(f"  [FAIL] 连接失败: {err}")
        if "password" in err.lower() or "auth" in err.lower():
            safe_print("  建议: 检查 .env 中 POSTGRES_PASSWORD 与数据库用户密码是否一致")
        if "does not exist" in err or "database" in err.lower():
            safe_print("  建议: 在 Postgres 中创建数据库: CREATE DATABASE xihong_erp;")
        if "role" in err.lower() or "user" in err.lower():
            safe_print("  建议: 在 Postgres 中创建用户并授权，或使用现有用户并修正 .env 中的 POSTGRES_USER/POSTGRES_PASSWORD")
        sys.exit(1)
    safe_print("  [OK] 数据库连接成功")

    safe_print("\n" + "=" * 60)
    safe_print("[OK] 本地 Postgres + .env 满足后端启动要求，可运行: python local_run.py")
    safe_print("=" * 60)


if __name__ == "__main__":
    main()
