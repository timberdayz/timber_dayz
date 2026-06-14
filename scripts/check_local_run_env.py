#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Validate local startup requirements for default and collection profiles."""

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


def validate_collection_profile(require_tunnel_reachable: bool = False) -> Tuple[bool, list[str]]:
    errors: list[str] = []

    if not _is_truthy(os.getenv("ENABLE_COLLECTION")):
        errors.append("ENABLE_COLLECTION must be true")

    if not _is_truthy(os.getenv("CLOUD_SYNC_WORKER_ENABLED")):
        errors.append("CLOUD_SYNC_WORKER_ENABLED must be true")

    if not os.getenv("CLOUD_DATABASE_URL", "").strip():
        errors.append("CLOUD_DATABASE_URL is required for cloud sync")

    tunnel_enabled = _is_truthy(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED"))
    tunnel_host = os.getenv("CLOUD_SYNC_TUNNEL_HOST", "").strip()
    tunnel_port = os.getenv("CLOUD_SYNC_TUNNEL_PORT", "").strip()

    if tunnel_enabled:
        if not tunnel_host:
            errors.append("CLOUD_SYNC_TUNNEL_HOST is required when tunnel is enabled")
        if not tunnel_port:
            errors.append("CLOUD_SYNC_TUNNEL_PORT is required when tunnel is enabled")

    if require_tunnel_reachable:
        if not tunnel_enabled:
            errors.append("CLOUD_SYNC_TUNNEL_ENABLED must be true in formal collection mode")
        elif tunnel_host and tunnel_port:
            try:
                parsed_tunnel_port = int(tunnel_port)
            except ValueError:
                errors.append("CLOUD_SYNC_TUNNEL_PORT must be an integer")
            else:
                if not check_tcp(tunnel_host, parsed_tunnel_port):
                    errors.append(f"CLOUD_SYNC_TUNNEL {tunnel_host}:{parsed_tunnel_port} is not reachable")

    return not errors, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local runtime environment")
    parser.add_argument(
        "--profile",
        choices=["default", "collection"],
        default="default",
        help="collection also loads .env.collection.local and validates collection/cloud-sync settings",
    )
    parser.add_argument(
        "--require-cloud-tunnel",
        action="store_true",
        help="require CLOUD_SYNC_TUNNEL_HOST:PORT to be reachable before startup",
    )
    args = parser.parse_args()

    load_project_env(project_root, profile=None if args.profile == "default" else args.profile)

    safe_print("=" * 60)
    safe_print("Local startup environment check")
    safe_print("=" * 60)

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        safe_print("[FAIL] DATABASE_URL is not set")
        safe_print("  Hint: configure DATABASE_URL=postgresql://... in .env")
        sys.exit(1)

    if not url.startswith("postgresql"):
        safe_print(f"[FAIL] DATABASE_URL is not PostgreSQL: {url[:50]}...")
        sys.exit(1)

    info = parse_pg_url(url)
    if not info:
        safe_print("[FAIL] DATABASE_URL could not be parsed")
        sys.exit(1)

    safe_print("\n[Config] Current database")
    safe_print(f"  Host: {info['host']}")
    safe_print(f"  Port: {info['port']}")
    safe_print(f"  User: {info['user']}")
    safe_print(f"  Database: {info['dbname']}")
    safe_print("  Password: ****")

    safe_print("\n[Check] TCP connectivity ...")
    if not check_tcp(info["host"], info["port"]):
        safe_print(f"  [FAIL] Cannot connect to {info['host']}:{info['port']}")
        if info["port"] == 15432:
            safe_print("  Hint: start the Docker postgres dev service first.")
        sys.exit(1)
    safe_print("  [OK] Port reachable")

    safe_print("\n[Check] PostgreSQL auth ...")
    ok, err = check_postgres_connect(url)
    if not ok:
        safe_print(f"  [FAIL] Connection failed: {err}")
        sys.exit(1)
    safe_print("  [OK] Database connection succeeded")

    if args.profile == "collection":
        safe_print("\n[Check] Collection/cloud-sync switches ...")
        ok, errors = validate_collection_profile(require_tunnel_reachable=args.require_cloud_tunnel)
        if not ok:
            for error in errors:
                safe_print(f"  [FAIL] {error}")
            sys.exit(1)
        safe_print("  [OK] Collection/cloud-sync settings are enabled")

    safe_print("\n" + "=" * 60)
    safe_print("[OK] Local runtime environment check passed")
    safe_print("=" * 60)


if __name__ == "__main__":
    main()
