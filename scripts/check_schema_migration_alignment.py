#!/usr/bin/env python3
"""Fail if a model change ships without a current-schema migration.

Production runs the migration chain under current_migrations/ via
alembic-current.ini. The legacy migrations/ directory is read-only
historical archive and is never applied at deploy time. This check
makes that contract explicit at PR/CI time:

- If modules/core/db/schema_parts/** changed in the diff against BASE_REF,
  then current_migrations/versions/** must also have changed.

Exits 0 when aligned, 1 with a clear message when not.

Usage:
    python scripts/check_schema_migration_alignment.py [--base origin/main]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PARTS_GLOB = "modules/core/db/schema_parts/"
CURRENT_VERSIONS_GLOB = "current_migrations/versions/"


def _changed_files(base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"[FAIL] git diff {base_ref}...HEAD failed: {result.stderr.strip()}")
        sys.exit(1)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="git base ref for diff")
    args = parser.parse_args()

    changed = _changed_files(args.base)
    schema_changed = [f for f in changed if f.startswith(SCHEMA_PARTS_GLOB) and f.endswith(".py")]
    migration_changed = [f for f in changed if f.startswith(CURRENT_VERSIONS_GLOB) and f.endswith(".py")]

    if not schema_changed:
        print(f"[OK] no model changes under {SCHEMA_PARTS_GLOB} since {args.base}; nothing to align.")
        return 0

    if not migration_changed:
        print(
            "[FAIL] model files changed but no current-schema migration added.\n"
            f"  changed models:    {len(schema_changed)}\n"
            f"  changed migrations: 0 (under {CURRENT_VERSIONS_GLOB})\n"
            "  fix: add a new file under current_migrations/versions/, "
            "down_revision = current_schema_20260921_warehouse_storage_label_fee.\n"
            "  legacy migrations/ is read-only and will not run in production.",
        )
        return 1

    print(
        f"[OK] {len(schema_changed)} model file(s) and "
        f"{len(migration_changed)} current-schema migration(s) changed since {args.base}.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
