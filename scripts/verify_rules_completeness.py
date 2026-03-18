"""
verify_rules_completeness.py

Validate that the repository's active rule files stay aligned with the
skill-first workflow.

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
    ".cursorrules": PROJECT_ROOT / ".cursorrules",
    "skill-integration.mdc": PROJECT_ROOT / ".cursor" / "rules" / "skill-integration.mdc",
    "docs/DEVELOPMENT_RULES/README.md": PROJECT_ROOT / "docs" / "DEVELOPMENT_RULES" / "README.md",
    "docs/superpowers/README.md": PROJECT_ROOT / "docs" / "superpowers" / "README.md",
    "docs/guides/DEVELOPMENT_RULES.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_RULES.md",
}

REQUIRED_PHRASES = {
    "AGENTS.md": [
        "skill-first workflow",
        "`superpowers`",
        "`planning-with-files`",
        "historical archive",
        "openspec/",
        "Chinese",
    ],
    "CLAUDE.md": [
        "This repository is now skill-first",
        "`brainstorming` -> `writing-plans`",
        "`planning-with-files`",
        "Always answer users in Chinese",
        "Historical archive only",
    ],
    ".cursorrules": [
        "repository-specific constraints only",
        "task_plan.md",
        "async_playwright",
        "Vue 3 + Element Plus + Pinia + Vite",
        "openspec/",
    ],
    "skill-integration.mdc": [
        "Use `superpowers` as the default workflow engine.",
        "docs/superpowers/specs/",
        "`task_plan.md`, `findings.md`, and `progress.md` intentionally live in project root.",
        "OpenSpec Status",
    ],
    "docs/DEVELOPMENT_RULES/README.md": [
        "Active workflow: `superpowers` + `planning-with-files`",
        "Historical archive",
    ],
    "docs/superpowers/README.md": [
        "active `superpowers` workflow",
        "`planning-with-files`",
    ],
    "docs/guides/DEVELOPMENT_RULES.md": [
        "historical snapshot",
        "Do not use it as the active rule source.",
    ],
}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    missing_files: list[str] = []
    missing_phrases: list[tuple[str, str]] = []

    for name, path in REQUIRED_FILES.items():
        if not path.exists():
            missing_files.append(f"{name}: {path}")
            continue

        content = load_text(path)
        for phrase in REQUIRED_PHRASES.get(name, []):
            if phrase not in content:
                missing_phrases.append((name, phrase))

    if missing_files:
        print("[FAIL] Missing required rule files:")
        for item in missing_files:
            print(f"  - {item}")

    if missing_phrases:
        print("[FAIL] Missing required rule phrases:")
        for file_name, phrase in missing_phrases:
            print(f'  - {file_name}: "{phrase}"')

    if missing_files or missing_phrases:
        return 1

    print("[PASS] Skill-first rule files are present and aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
