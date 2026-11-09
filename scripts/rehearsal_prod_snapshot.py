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
1) Run the fail-closed current-schema migration entrypoint against the snapshot DB
2) Run PostgreSQL Dashboard assets bootstrap once (idempotent, lock-safe)

Fail-closed contract (2026-11-09):
- Missing required env => NON-ZERO exit and an explicit list of what is missing.
  A rehearsal that never ran must never look like a rehearsal that passed
  ("兜底即伪装"). Previously this script printed ``[SKIP]`` and returned 0, so a
  release could be declared green while zero migrations were rehearsed.
- ``--allow-skip`` is the ONLY way to accept "not rehearsed" as success. It is
  meant for the LOCAL verification chain (``scripts/verify_release_local.py``),
  where the snapshot DB is optional. PRODUCTION / release chains must NOT pass
  it: there, an unrehearsed release must fail loudly.

Exit code:
- 0: rehearsal ok (or explicitly skipped via --allow-skip)
- 2: missing env / invalid inputs
- 1: rehearsal failed
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

REQUIRED_ENV_VARS = ("PROD_SNAPSHOT_DATABASE_URL",)
ALLOWED_DB_URL_SCHEMES = ("postgresql://", "postgresql+asyncpg://")


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _run(cmd: list[str], *, env: dict[str, str], cwd: Path) -> None:
    subprocess.run(cmd, env=env, cwd=str(cwd), check=True)


def _missing_requirements() -> list[str]:
    """Collect every unmet precondition, so one run tells the operator everything."""
    missing: list[str] = []
    for name in REQUIRED_ENV_VARS:
        if not _env(name):
            missing.append(f"{name} (not set)")
    return missing


def _validate_db_url(db_url: str) -> str | None:
    if not db_url.startswith(ALLOWED_DB_URL_SCHEMES):
        return (
            "PROD_SNAPSHOT_DATABASE_URL must start with "
            f"{' or '.join(ALLOWED_DB_URL_SCHEMES)}"
        )
    return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help=(
            "Accept a missing snapshot database as a skip instead of a failure. "
            "Local verification chains only; production/release chains must not use it."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    db_url = _env("PROD_SNAPSHOT_DATABASE_URL")
    missing = _missing_requirements()
    if missing:
        print("[FAIL] Production snapshot rehearsal cannot run. Missing requirements:")
        for item in missing:
            print(f"  - {item}")
        print(
            "[INFO] Provide a restored snapshot database, for example: "
            "PROD_SNAPSHOT_DATABASE_URL=postgresql://user:pass@127.0.0.1:15432/snapshot"
        )
        if args.allow_skip:
            print("[SKIP] Snapshot rehearsal skipped because --allow-skip was passed.")
            return 0
        print(
            "[FAIL] Snapshot rehearsal did not run. "
            "Do not treat this release as rehearsed."
        )
        return 2

    url_error = _validate_db_url(db_url or "")
    if url_error:
        print(f"[FAIL] {url_error}")
        return 2

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url or ""
    # Explicitly disable any startup-time bootstrap side effects; we control the flow here.
    env.setdefault("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", "false")

    try:
        print("[INFO] Rehearsal: current-schema migration on snapshot DB...")
        _run(
            [
                sys.executable,
                str(ROOT_DIR / "scripts" / "run_current_schema_migrations.py"),
            ],
            env=env,
            cwd=ROOT_DIR,
        )

        print(
            "[INFO] Rehearsal: bootstrap PostgreSQL Dashboard assets on snapshot DB..."
        )
        _run(
            [
                sys.executable,
                str(ROOT_DIR / "scripts" / "bootstrap_postgresql_dashboard.py"),
            ],
            env=env,
            cwd=ROOT_DIR,
        )

        print("[OK] Snapshot rehearsal passed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"[FAIL] Snapshot rehearsal failed (exit={exc.returncode}).")
        return 1
    except OSError as exc:
        print(f"[FAIL] Snapshot rehearsal could not start ({exc}).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
