"""
verify_rules_completeness.py

Validate that the repository's active rule files stay aligned with the
Codex-first rule model.

Usage:
    python scripts/verify_rules_completeness.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = {
    "AGENTS.md": PROJECT_ROOT / "AGENTS.md",
    "CLAUDE.md": PROJECT_ROOT / "CLAUDE.md",
    "docs/DEVELOPMENT_RULES/README.md": PROJECT_ROOT / "docs" / "DEVELOPMENT_RULES" / "README.md",
    "docs/superpowers/README.md": PROJECT_ROOT / "docs" / "superpowers" / "README.md",
    "docs/guides/DEVELOPMENT_RULES.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_RULES.md",
    "docs/guides/DEVELOPMENT_WORKFLOW.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_WORKFLOW.md",
    "docs/guides/PRE_LAUNCH_RULES.md": PROJECT_ROOT / "docs" / "guides" / "PRE_LAUNCH_RULES.md",
    "docs/architecture/README.md": PROJECT_ROOT / "docs" / "architecture" / "README.md",
    "docs/architecture/DASHBOARD.md": PROJECT_ROOT / "docs" / "architecture" / "DASHBOARD.md",
}

RETIRED_FILES = {
    ".cursorrules": PROJECT_ROOT / ".cursorrules",
    ".cursor/rules/skill-integration.mdc": PROJECT_ROOT / ".cursor" / "rules" / "skill-integration.mdc",
}

REQUIRED_PHRASES = {
    "AGENTS.md": [
        "single active rule entrypoint",
        "Primary development agent: Codex",
        "Cursor is not part of the active workflow",
        "`superpowers`",
        "`planning-with-files`",
        "Pre-Launch Development Constraints",
        "Answer users in Chinese",
    ],
    "CLAUDE.md": [
        "`AGENTS.md` as the single active rule entrypoint",
        "Claude is a supplemental assistant",
        "Do not treat `.cursorrules`",
    ],
    "docs/DEVELOPMENT_RULES/README.md": [
        "Active rule entrypoint",
        "Cursor rule files are not part of the active workflow",
    ],
    "docs/superpowers/README.md": [
        "active `superpowers` workflow",
        "`planning-with-files`",
    ],
    "docs/guides/DEVELOPMENT_RULES.md": [
        "historical snapshot",
        "Do not use it as the active rule source.",
    ],
    "docs/guides/DEVELOPMENT_WORKFLOW.md": [
        "Repository rules live in `AGENTS.md`",
        "Production deployment is tag-driven",
    ],
    "docs/guides/PRE_LAUNCH_RULES.md": [
        "until the first production launch is stable",
        "Prohibited Changes",
    ],
    "docs/architecture/README.md": [
        "The active repository rule entrypoint is `AGENTS.md`",
        "ORM source of truth",
    ],
    "docs/architecture/DASHBOARD.md": [
        "PostgreSQL-first",
        "Metabase is historical-only",
    ],
}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    missing_files: list[str] = []
    unexpected_files: list[str] = []
    missing_phrases: list[tuple[str, str]] = []

    for name, path in REQUIRED_FILES.items():
        if not path.exists():
            missing_files.append(f"{name}: {path}")
            continue

        content = load_text(path)
        for phrase in REQUIRED_PHRASES.get(name, []):
            if phrase not in content:
                missing_phrases.append((name, phrase))

    for name, path in RETIRED_FILES.items():
        if path.exists():
            unexpected_files.append(f"{name}: {path}")

    if missing_files:
        print("[FAIL] Missing required rule files:")
        for item in missing_files:
            print(f"  - {item}")

    if unexpected_files:
        print("[FAIL] Retired Cursor rule files are still active:")
        for item in unexpected_files:
            print(f"  - {item}")

    if missing_phrases:
        print("[FAIL] Missing required rule phrases:")
        for file_name, phrase in missing_phrases:
            print(f'  - {file_name}: "{phrase}"')

    if missing_files or unexpected_files or missing_phrases:
        return 1

    print("[PASS] Rule files match the Codex-first model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
