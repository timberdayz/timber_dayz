#!/usr/bin/env python3
"""
Validate root Markdown file hygiene.

Long-form reports and historical notes should live under docs/ or archive/.
"""

from __future__ import annotations

import sys
from pathlib import Path


ALLOWED = {
    "AGENTS.md",
    "API_CONTRACT.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "FIELD_DICTIONARY_REFERENCE.md",
    "README.md",
    "findings.md",
    "progress.md",
    "task_plan.md",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    md_files = sorted(path.name for path in root.glob("*.md"))
    violations = [file_name for file_name in md_files if file_name not in ALLOWED]

    if violations:
        print("[ERROR] Root Markdown files outside the allowlist:")
        for file_name in violations:
            print(f"  - {file_name}")
        print("Move long-form reports to docs/ or archive/, or update the allowlist intentionally.")
        return 1

    print("[OK] Root Markdown allowlist check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
