#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Local verification helper for B-class cloud sync."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from sqlalchemy.engine import make_url

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify local-to-cloud B-class sync against a local target DB")
    parser.add_argument("--verify-db", default="xihong_erp_cloud_sync_verify")
    parser.add_argument("--table", default=None)
    return parser.parse_args(argv)


def _run_command(command: list[str], env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(command, cwd=project_root, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}")


def _load_local_database_url(root: Path) -> str | None:
    env_file = root / ".env"
    if not env_file.exists():
        return None

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DATABASE_URL":
            return value.strip().strip('"')
    return None


def _build_verify_database_url(verify_db: str) -> str:
    override_url = os.getenv("CLOUD_SYNC_VERIFY_DATABASE_URL")
    if override_url:
        return override_url

    local_database_url = os.getenv("DATABASE_URL") or _load_local_database_url(project_root)
    if local_database_url:
        parsed = make_url(local_database_url)
        if parsed.drivername.split("+", 1)[0] == "postgresql":
            auth = ""
            if parsed.username:
                auth = quote(parsed.username, safe="")
                if parsed.password is not None:
                    auth = f"{auth}:{quote(parsed.password, safe='')}"
                auth = f"{auth}@"
            host = parsed.host or "localhost"
            port = parsed.port or 15432
            return f"postgresql://{auth}{host}:{port}/{verify_db}"

    return f"postgresql://localhost:15432/{verify_db}"


def run_verification(*, verify_db: str, table: str | None) -> bool:
    _run_command([sys.executable, "scripts/migrate_cloud_sync_tables.py"])
    _run_command([sys.executable, "scripts/sync_b_class_to_cloud.py", "--dry-run", "--batch-size", "10"])

    if table:
        env = dict(os.environ)
        env["CLOUD_DATABASE_URL"] = _build_verify_database_url(verify_db)
        _run_command(
            [
                sys.executable,
                "scripts/sync_b_class_to_cloud.py",
                "--table",
                table,
                "--batch-size",
                "500",
            ],
            env=env,
        )

    return True


def main(
    argv: list[str] | None = None,
    runner=run_verification,
) -> int:
    args = parse_args(argv)
    ok = runner(verify_db=args.verify_db, table=args.table)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
