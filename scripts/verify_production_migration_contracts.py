#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Run targeted production migration contract tests."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from sqlalchemy import create_engine, text


DEFAULT_TESTS = [
    "tests/test_alembic_version_table_contract.py",
    "tests/test_collection_config_core_schema_migration_contract.py",
    "tests/test_follow_investment_finance_schema_contract.py",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run production migration contract tests")
    parser.add_argument("--db-host", default=os.getenv("TEST_DB_HOST", "127.0.0.1"))
    parser.add_argument("--db-port", default=os.getenv("TEST_DB_PORT", "5432"))
    parser.add_argument("--db-user", default=os.getenv("TEST_DB_USER", "migration_test_user"))
    parser.add_argument("--db-password", default=os.getenv("TEST_DB_PASSWORD", "migration_test_pass"))
    parser.add_argument("--db-name", default=os.getenv("TEST_DB_NAME", "migration_test_db"))
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser.parse_args(argv)


def _run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(command, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}")


def postgres_ready_with_sqlalchemy(
    *,
    db_host: str,
    db_port: str,
    db_user: str,
    db_password: str,
    db_name: str,
) -> bool:
    database_url = (
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def wait_for_postgres_ready(
    *,
    db_host: str,
    db_port: str,
    db_user: str,
    db_password: str,
    db_name: str,
    timeout_seconds: int,
    runner=_run_command,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if postgres_ready_with_sqlalchemy(
                db_host=db_host,
                db_port=db_port,
                db_user=db_user,
                db_password=db_password,
                db_name=db_name,
            ):
                return True
        except Exception:
            pass
        try:
            env = dict(os.environ)
            env["PGPASSWORD"] = db_password
            runner(
                [
                    "psql",
                    "-h",
                    db_host,
                    "-p",
                    str(db_port),
                    "-U",
                    db_user,
                    "-d",
                    db_name,
                    "-c",
                    "SELECT 1",
                ],
                env=env,
            )
            return True
        except RuntimeError:
            time.sleep(1)
    return False


def run_contracts(args: argparse.Namespace, runner=_run_command) -> bool:
    ready = wait_for_postgres_ready(
        db_host=args.db_host,
        db_port=args.db_port,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        timeout_seconds=args.timeout_seconds,
        runner=runner,
    )
    if not ready:
        raise RuntimeError("PostgreSQL startup timeout")

    runner([sys.executable, "-m", "pytest", "-q", *DEFAULT_TESTS])
    return True


def main(argv: list[str] | None = None, runner=_run_command) -> int:
    args = parse_args(argv)
    ok = run_contracts(args, runner=runner)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
