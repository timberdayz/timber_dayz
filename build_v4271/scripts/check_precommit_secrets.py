"""
Cross-platform pre-commit secret file check.

Blocks obvious sensitive file types from being committed by mistake.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_BASENAMES = {
    "env.template",
    ".env.template",
}
ALLOWED_SUFFIXES = {
    ".example",
    ".template",
}


def is_blocked(path: Path) -> bool:
    name = path.name
    lower_name = name.lower()

    if lower_name in ALLOWED_BASENAMES:
        return False

    if any(lower_name.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
        return False

    if lower_name == ".env":
        return True

    return path.suffix.lower() in {".key", ".enc"}


def staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [PROJECT_ROOT / path for path in paths]


def main() -> int:
    blocked: list[Path] = []

    for path in staged_files():
        if not path.exists() or not path.is_file():
            continue
        if is_blocked(path):
            blocked.append(path.relative_to(PROJECT_ROOT))

    if blocked:
        print("[FAIL] Sensitive files detected:")
        for path in sorted(blocked):
            print(f"  - {path}")
        print("[INFO] Remove or ignore these files before commit.")
        return 1

    print("[PASS] No blocked secret files detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
