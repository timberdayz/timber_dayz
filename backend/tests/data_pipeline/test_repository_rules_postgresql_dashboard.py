from pathlib import Path


def test_repository_rule_files_reference_postgresql_dashboard_architecture():
    files = {
        "AGENTS.md": [
            "Dashboard",
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "Metabase",
        ],
        ".cursorrules": [
            "Dashboard",
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "USE_POSTGRESQL_DASHBOARD_ROUTER",
        ],
        "CLAUDE.md": [
            "Dashboard",
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "USE_POSTGRESQL_DASHBOARD_ROUTER",
        ],
        ".cursor/rules/skill-integration.mdc": [
            "Dashboard",
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
        ],
        "docs/DEVELOPMENT_RULES/README.md": [
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "dashboard",
        ],
    }

    for path_str, required_terms in files.items():
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        for term in required_terms:
            assert term in text
