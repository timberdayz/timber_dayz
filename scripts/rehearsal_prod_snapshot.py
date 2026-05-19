#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Production Snapshot Rehearsal (Local Only)

Goal:
- Run a deterministic "release rehearsal" against a production-like snapshot database
  BEFORE tagging and deploying.

This script intentionally DOES NOT restore dumps automatically.
It expects you to provide a ready-to-connect snapshot database via:

  PROD_SNAPSHOT_DATABASE_URL=postgresql+asyncpg://...  (or postgresql://...)

It will then:
1) Run Alembic upgrade heads against the snapshot DB
2) Run PostgreSQL Dashboard assets bootstrap once (idempotent, lock-safe)

Exit code:
- 0: rehearsal ok
- 2: missing env / invalid inputs
- 1: rehearsal failed
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _run(cmd: list[str], *, env: dict[str, str], cwd: Path) -> None:
    subprocess.run(cmd, env=env, cwd=str(cwd), check=True)


def main() -> int:
    db_url = _env("PROD_SNAPSHOT_DATABASE_URL")
    if not db_url:
        print("[SKIP] PROD_SNAPSHOT_DATABASE_URL not set; snapshot rehearsal skipped.")
        return 0

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    # Explicitly disable any startup-time bootstrap side effects; we control the flow here.
    env.setdefault("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", "false")

    try:
        print("[INFO] Rehearsal: alembic upgrade heads on snapshot DB...")
        _run(
            [sys.executable, "-m", "alembic", "upgrade", "heads"],
            env=env,
            cwd=ROOT_DIR,
        )

        print("[INFO] Rehearsal: bootstrap PostgreSQL Dashboard assets on snapshot DB...")
        _run(
            [sys.executable, str(ROOT_DIR / "scripts" / "bootstrap_postgresql_dashboard.py")],
            env=env,
            cwd=ROOT_DIR,
        )

        print("[OK] Snapshot rehearsal passed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"[FAIL] Snapshot rehearsal failed (exit={exc.returncode}).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

