#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.config import get_settings
from modules.utils.sessions.legacy_shop_artifact_cleanup import (
    collect_legacy_shop_artifacts_for_active_shops,
)


def delete_artifact(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=False)
        return
    path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean legacy shop-account-scoped session/profile/fingerprint artifacts."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete matched artifacts. Default is dry-run.",
    )
    args = parser.parse_args()

    settings = get_settings()
    project_root = PROJECT_ROOT
    artifacts = collect_legacy_shop_artifacts_for_active_shops(
        project_root,
        settings.DATABASE_URL,
    )

    print("Legacy shop-scoped artifacts:")
    if not artifacts:
        print("(none)")
        return 0

    for artifact in artifacts:
        print(artifact)

    if not args.delete:
        print("\nDry-run only. Re-run with --delete to remove these artifacts.")
        return 0

    for artifact in artifacts:
        delete_artifact(artifact)

    print(f"\nDeleted {len(artifacts)} artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
