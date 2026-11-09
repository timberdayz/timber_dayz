#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Run the repository's current pre-release local verification chain."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local pre-release verification")
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip production image build step"
    )
    parser.add_argument(
        "--table",
        default="fact_shopee_orders_monthly",
        help="B-class table used for local cloud-sync verification",
    )
    return parser.parse_args(argv)


def _run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}"
        )


def _build_verify_database_url_from_env(env_file: Path) -> str | None:
    if not env_file.exists():
        return None

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')

    database_url = values.get("DATABASE_URL")
    if not database_url:
        return None

    return database_url


def run_release_verification(*, skip_build: bool, table: str) -> bool:
    env_file = PROJECT_ROOT / ".env.production"

    _run_command([sys.executable, "scripts/verify_release_tag_generation.py"])
    _run_command([sys.executable, "scripts/verify_remote_deploy_contracts.py"])
    _run_command(
        [sys.executable, "scripts/verify_system_role_integrity.py", "--repair"]
    )
    _run_command([sys.executable, "scripts/validate_production_env.py"])
    _run_command([sys.executable, "scripts/pre_deployment_check.py"])
    _run_command([sys.executable, "scripts/validate_migrations_fresh_db.py"])

    # [*] ORM ↔ 数据库 结构漂移体检（fail-closed）
    # ORM 声明的列必须真实存在于库里，否则代码一用到就抛
    # UndefinedColumnError，现场表现为接口 500
    # （历史现场：/api/hr/attendance 报 attendance_records.employee_code 不存在）。
    # 没有 DATABASE_URL 时体检脚本退出码为 2，不静默跳过 —— 发版必须先体检通过。
    drift_env = dict(os.environ)
    verify_database_url = _build_verify_database_url_from_env(PROJECT_ROOT / ".env")
    if verify_database_url:
        drift_env["DATABASE_URL"] = verify_database_url
    _run_command([sys.executable, "scripts/verify_orm_schema_drift.py"], env=drift_env)

    compose_env = dict(os.environ)
    compose_env["COMPOSE_PROFILES"] = "production"
    _run_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.prod.yml",
            "-f",
            "docker-compose.verify-local.yml",
            "--profile",
            "production",
            "config",
            "--quiet",
        ],
        env=compose_env,
    )

    if not skip_build:
        _run_command(
            [
                "docker",
                "compose",
                "--env-file",
                str(env_file),
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.prod.yml",
                "-f",
                "docker-compose.verify-local.yml",
                "--profile",
                "production",
                "build",
                "backend-api",
                "migrate",
                "frontend",
            ],
            env=compose_env,
        )

    verify_env = dict(os.environ)
    verify_database_url = _build_verify_database_url_from_env(PROJECT_ROOT / ".env")
    if verify_database_url:
        verify_env["DATABASE_URL"] = verify_database_url
    _run_command(
        [
            sys.executable,
            "scripts/verify_cloud_sync_local.py",
            "--verify-db",
            "xihong_erp_cloud_sync_verify",
            "--table",
            table,
        ],
        env=verify_env,
    )

    # Optional: run a full rehearsal against a locally-restored production snapshot DB.
    # Set PROD_SNAPSHOT_DATABASE_URL to enable.
    # 本地链允许"没有快照库"= 跳过（--allow-skip）；生产/发版链**不得**传这个开关，
    # 那里"没演练"必须是非零退出，不能伪装成演练通过。
    _run_command([sys.executable, "scripts/rehearsal_prod_snapshot.py", "--allow-skip"])

    return True


def main(argv: list[str] | None = None, runner=run_release_verification) -> int:
    args = parse_args(argv)
    ok = runner(skip_build=args.skip_build, table=args.table)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
