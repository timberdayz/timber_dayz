#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Local verification helper for B-class cloud sync."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

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


def run_verification(*, verify_db: str, table: str | None) -> bool:
    _run_command([sys.executable, "scripts/migrate_cloud_sync_tables.py"])
    _run_command([sys.executable, "scripts/sync_b_class_to_cloud.py", "--dry-run", "--batch-size", "10"])

    if table:
        env = dict(os.environ)
        env["CLOUD_DATABASE_URL"] = f"postgresql://erp_user:erp_pass_2025@localhost:15432/{verify_db}"
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
