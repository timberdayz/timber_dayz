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
    "docs/ACTIVE_DOCS.md": PROJECT_ROOT / "docs" / "ACTIVE_DOCS.md",
    "docs/DEVELOPMENT_RULES/README.md": PROJECT_ROOT / "docs" / "DEVELOPMENT_RULES" / "README.md",
    "docs/superpowers/README.md": PROJECT_ROOT / "docs" / "superpowers" / "README.md",
    "docs/guides/DEVELOPMENT_RULES.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_RULES.md",
    "docs/guides/DEVELOPMENT_WORKFLOW.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_WORKFLOW.md",
    "docs/guides/PRE_LAUNCH_RULES.md": PROJECT_ROOT / "docs" / "guides" / "PRE_LAUNCH_RULES.md",
    "docs/guides/ENVIRONMENT_MODEL.md": PROJECT_ROOT / "docs" / "guides" / "ENVIRONMENT_MODEL.md",
    "docs/guides/DEVELOPMENT_ENVIRONMENT.md": PROJECT_ROOT / "docs" / "guides" / "DEVELOPMENT_ENVIRONMENT.md",
    "docs/guides/ENV_FILE_CONTRACT.md": PROJECT_ROOT / "docs" / "guides" / "ENV_FILE_CONTRACT.md",
    "docs/guides/AGENT_TASK_CONTRACT.md": PROJECT_ROOT / "docs" / "guides" / "AGENT_TASK_CONTRACT.md",
    "docs/guides/COLLECTION_AUTHORING_RULES.md": PROJECT_ROOT / "docs" / "guides" / "COLLECTION_AUTHORING_RULES.md",
    "docs/guides/PWCLI_COMMAND_REFERENCE.md": PROJECT_ROOT / "docs" / "guides" / "PWCLI_COMMAND_REFERENCE.md",
    "docs/guides/CHANGE_CONTROL.md": PROJECT_ROOT / "docs" / "guides" / "CHANGE_CONTROL.md",
    "docs/guides/VERIFICATION_MATRIX.md": PROJECT_ROOT / "docs" / "guides" / "VERIFICATION_MATRIX.md",
    "docs/guides/DOCUMENT_LIFECYCLE.md": PROJECT_ROOT / "docs" / "guides" / "DOCUMENT_LIFECYCLE.md",
    "docs/architecture/README.md": PROJECT_ROOT / "docs" / "architecture" / "README.md",
    "docs/architecture/PROJECT_STRUCTURE.md": PROJECT_ROOT / "docs" / "architecture" / "PROJECT_STRUCTURE.md",
    "docs/architecture/DASHBOARD.md": PROJECT_ROOT / "docs" / "architecture" / "DASHBOARD.md",
    "docs/architecture/BOUNDARIES.md": PROJECT_ROOT / "docs" / "architecture" / "BOUNDARIES.md",
    "docs/adr/README.md": PROJECT_ROOT / "docs" / "adr" / "README.md",
    "scripts/verify_pwcli_helpers.ps1": PROJECT_ROOT / "scripts" / "verify_pwcli_helpers.ps1",
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
        "Superpowers Repository Adapters",
        "docs/ACTIVE_DOCS.md",
        "docs/guides/DEVELOPMENT_ENVIRONMENT.md",
        "docs/guides/ENV_FILE_CONTRACT.md",
        "docs/guides/COLLECTION_AUTHORING_RULES.md",
        "docs/guides/PWCLI_COMMAND_REFERENCE.md",
        "docs/architecture/PROJECT_STRUCTURE.md",
        "Answer users in Chinese",
    ],
    "CLAUDE.md": [
        "`AGENTS.md` as the single active rule entrypoint",
        "Claude is a supplemental assistant",
        "Do not treat `.cursorrules`",
    ],
    "docs/ACTIVE_DOCS.md": [
        "current documentation entrypoints agents should prefer",
        "Rule And Agent Context",
        "ENV_FILE_CONTRACT.md",
        "COLLECTION_AUTHORING_RULES.md",
        "Historical material is useful for traceability",
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
    "docs/guides/ENVIRONMENT_MODEL.md": [
        "repository adapter for `superpowers`",
        "Production Collection Runtime",
    ],
    "docs/guides/DEVELOPMENT_ENVIRONMENT.md": [
        "agent-facing baseline for local development environment assumptions",
        "Python 3.13.13",
        "Node.js 24.14.0",
        "python run.py --local",
        "Playwright",
        "ENV_FILE_CONTRACT.md",
    ],
    "docs/guides/ENV_FILE_CONTRACT.md": [
        "Do not commit real secrets",
        ".env.production.passwords.txt",
        "env.production.cloud.example",
        "state which environment is affected",
    ],
    "docs/guides/AGENT_TASK_CONTRACT.md": [
        "repository adapter for `superpowers`",
        "Recommended Task Fields",
    ],
    "docs/guides/COLLECTION_AUTHORING_RULES.md": [
        "active, clean entrypoint for collection authoring",
        "modules/platforms/<platform>/components/",
        "Do not use legacy recorder flows",
        "legacy long-form material",
    ],
    "docs/guides/PWCLI_COMMAND_REFERENCE.md": [
        "agent-facing command reference for `pwcli`, `pwcap`",
        "Get-Command pwcli",
        "pwcap",
        "verify_pwcli_helpers.ps1",
        "scripts/pw-cap.ps1",
        "Markdown artifacts",
    ],
    "docs/guides/CHANGE_CONTROL.md": [
        "not a replacement workflow",
        "V2 Rebuild Phase",
    ],
    "docs/guides/VERIFICATION_MATRIX.md": [
        "active verification workflow",
        "Collection Changes",
        "verify_pwcli_helpers.ps1",
    ],
    "docs/guides/DOCUMENT_LIFECYCLE.md": [
        "`AGENTS.md` is the only active rule entrypoint",
        "Reports And Historical Notes",
        "encoding damage",
    ],
    "docs/architecture/README.md": [
        "The active repository rule entrypoint is `AGENTS.md`",
        "ORM source of truth",
        "PROJECT_STRUCTURE.md",
    ],
    "docs/architecture/PROJECT_STRUCTURE.md": [
        "agent-facing map of repository ownership",
        "ORM SSOT is `modules/core/db/schema.py`",
        "Platform-specific canonical components belong in `modules/platforms/<platform>/components/`",
        "Frontend API access belongs in `frontend/src/api/`",
        "Do not add new root-level temporary reports",
    ],
    "docs/architecture/DASHBOARD.md": [
        "PostgreSQL-first",
        "Metabase is historical-only",
    ],
    "docs/architecture/BOUNDARIES.md": [
        "ownership boundaries for agents",
        "Collection",
    ],
    "docs/adr/README.md": [
        "Architecture Decision Records",
        "When To Add An ADR",
        "Accepted Decisions",
    ],
    "scripts/verify_pwcli_helpers.ps1": [
        "requiredHelpers",
        "pwcap",
        "requiredScripts",
        "[PASS] pwcli helper commands and fallback scripts are available",
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
