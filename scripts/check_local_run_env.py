#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
本地启动环境检查。

默认检查当前 `.env` / `.env.local` 是否满足本地后端启动要求。
当传入 `--profile collection` 时，还会加载 `.env.collection.local`
并额外校验临时采集顶替模式所需的关键开关。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.project_env import load_project_env


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)


def parse_pg_url(url: str) -> dict:
    if not url or not url.startswith("postgresql"):
        return {}
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port if parsed.port is not None else 5432
    user = parsed.username or "postgres"
    password = parsed.password or ""
    dbname = (parsed.path or "").strip("/") or "postgres"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
    }


def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except Exception:
        return False


def check_postgres_connect(url: str, timeout: int = 5) -> Tuple[bool, str]:
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, connect_args={"connect_timeout": timeout})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_collection_profile() -> Tuple[bool, list[str]]:
    errors: list[str] = []

    if not _is_truthy(os.getenv("ENABLE_COLLECTION")):
        errors.append("ENABLE_COLLECTION 必须为 true")

    if not _is_truthy(os.getenv("CLOUD_SYNC_WORKER_ENABLED")):
        errors.append("CLOUD_SYNC_WORKER_ENABLED 必须为 true")

    if not os.getenv("CLOUD_DATABASE_URL", "").strip():
        errors.append("CLOUD_DATABASE_URL 未配置，自动云端同步无法启用")

    if _is_truthy(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED")):
        if not os.getenv("CLOUD_SYNC_TUNNEL_HOST", "").strip():
            errors.append("CLOUD_SYNC_TUNNEL_HOST 未配置")
        if not os.getenv("CLOUD_SYNC_TUNNEL_PORT", "").strip():
            errors.append("CLOUD_SYNC_TUNNEL_PORT 未配置")

    return not errors, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="检查本地运行环境")
    parser.add_argument(
        "--profile",
        choices=["default", "collection"],
        default="default",
        help="collection 会额外校验本机顶替采集机所需配置",
    )
    args = parser.parse_args()

    load_project_env(project_root, profile=None if args.profile == "default" else args.profile)

    safe_print("=" * 60)
    safe_print("本地启动环境检查")
    safe_print("=" * 60)

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        safe_print("[FAIL] 未设置 DATABASE_URL")
        safe_print("  建议: 在项目根目录 .env 中配置 DATABASE_URL=postgresql://...")
        sys.exit(1)

    if not url.startswith("postgresql"):
        safe_print(f"[FAIL] 当前 DATABASE_URL 不是 PostgreSQL: {url[:50]}...")
        sys.exit(1)

    info = parse_pg_url(url)
    if not info:
        safe_print("[FAIL] 无法解析 DATABASE_URL")
        sys.exit(1)

    safe_print("\n[配置] 当前数据库配置")
    safe_print(f"  主机: {info['host']}")
    safe_print(f"  端口: {info['port']}")
    safe_print(f"  用户: {info['user']}")
    safe_print(f"  数据库: {info['dbname']}")
    safe_print("  密码: ****")

    safe_print("\n[检查] TCP 连接 ...")
    if not check_tcp(info["host"], info["port"]):
        safe_print(f"  [FAIL] 无法连接到 {info['host']}:{info['port']}")
        if info["port"] == 15432:
            safe_print("  提示: 如使用 Docker PostgreSQL，请先启动 dev profile 的 postgres。")
        sys.exit(1)
    safe_print("  [OK] 端口可达")

    safe_print("\n[检查] 数据库连接与认证 ...")
    ok, err = check_postgres_connect(url)
    if not ok:
        safe_print(f"  [FAIL] 连接失败: {err}")
        sys.exit(1)
    safe_print("  [OK] 数据库连接成功")

    if args.profile == "collection":
        safe_print("\n[检查] 采集顶替模式关键开关 ...")
        ok, errors = validate_collection_profile()
        if not ok:
            for error in errors:
                safe_print(f"  [FAIL] {error}")
            sys.exit(1)
        safe_print("  [OK] 采集/云端同步关键配置已启用")

    safe_print("\n" + "=" * 60)
    safe_print("[OK] 本地运行环境检查通过")
    safe_print("=" * 60)


if __name__ == "__main__":
    main()
