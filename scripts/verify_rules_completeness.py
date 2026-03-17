"""
verify_rules_completeness.py

Verifies that .cursorrules contains all zero-tolerance rule keywords
after simplification. Run after any edit to .cursorrules.

Usage:
    python scripts/verify_rules_completeness.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CURSORRULES_PATH = PROJECT_ROOT / ".cursorrules"

ZERO_TOLERANCE_KEYWORDS = {
    "architecture_ssot": {
        "keywords": ["schema.py", "SSOT", "modules/core/db"],
        "description": "ORM models only in schema.py (SSOT)",
    },
    "contract_first": {
        "keywords": ["Contract-First", "backend/schemas/", "response_model"],
        "description": "Pydantic models in schemas/, response_model required",
    },
    "layer_dependency": {
        "keywords": ["Frontend", "Backend", "Core"],
        "description": "Layer dependency: Frontend -> Backend -> Core",
    },
    "async_first": {
        "keywords": ["get_async_db", "AsyncSession", "await"],
        "description": "Async-first: get_async_db(), await db.execute()",
    },
    "no_sync_db": {
        "keywords": ["get_db"],
        "description": "Prohibit get_db() in new code",
    },
    "no_emoji": {
        "keywords": ["emoji", "UnicodeEncodeError"],
        "description": "No emoji in output (Windows encoding)",
    },
    "no_inline_pydantic": {
        "keywords": ["routers/"],
        "description": "No inline Pydantic models in routers/",
    },
    "playwright_official_api": {
        "keywords": ["Playwright", "get_by_role"],
        "description": "Playwright official API priority",
    },
    "async_playwright": {
        "keywords": ["async_playwright"],
        "description": "Must use async_playwright in FastAPI",
    },
    "collection_guide": {
        "keywords": ["COLLECTION_SCRIPT_WRITING_GUIDE"],
        "description": "Collection scripts must follow the guide",
    },
    "node_version": {
        "keywords": ["Node", "24"],
        "description": "Node.js 24+ required",
    },
    "error_handling_narrow": {
        "keywords": ["try-except", "ERROR_HANDLING"],
        "description": "Narrow exception scope, accurate error messages",
    },
    "no_backup_files": {
        "keywords": ["_backup", "legacy_"],
        "description": "No *_backup.py or legacy_* directories",
    },
    "no_new_base": {
        "keywords": ["declarative_base"],
        "description": "No new Base = declarative_base()",
    },
    "protected_directory": {
        "keywords": ["DEVELOPMENT_RULES"],
        "description": "docs/DEVELOPMENT_RULES/ is protected",
    },
    "logger_import": {
        "keywords": ["modules.core.logger", "get_logger"],
        "description": "Logger from modules.core.logger",
    },
    "alembic_migration": {
        "keywords": ["Alembic", "alembic"],
        "description": "Database changes via Alembic migration",
    },
    "no_heredoc_github_actions": {
        "keywords": ["heredoc", "GitHub Actions"],
        "description": "No heredoc in GitHub Actions workflows",
    },
    "datetime_standard": {
        "keywords": ["datetime.utcnow", "datetime.now(timezone.utc)"],
        "description": "Use datetime.now(timezone.utc), not utcnow()",
    },
    "crud_base_class": {
        "keywords": ["AsyncCRUDService"],
        "description": "New Services must inherit AsyncCRUDService",
    },
    "router_size_limit": {
        "keywords": ["15"],
        "description": "Router files <= 15 endpoints",
    },
    "service_di": {
        "keywords": ["Depends"],
        "description": "Service injection via Depends()",
    },
    "code_patterns_pointer": {
        "keywords": ["CODE_PATTERNS"],
        "description": "Pointer to CODE_PATTERNS.md for templates",
    },
    "local_refresh": {
        "keywords": ["loading"],
        "description": "Partial loading, no full-screen blocking",
    },
    "ci_cd_tag_deploy": {
        "keywords": ["git tag", "vX.Y.Z"],
        "description": "Production deploy via git tag only",
    },
    "executor_manager": {
        "keywords": ["ExecutorManager", "run_cpu_intensive"],
        "description": "CPU/IO tasks via ExecutorManager",
    },
}

MAX_LINES = 300


def verify():
    if not CURSORRULES_PATH.exists():
        print("[FAIL] .cursorrules not found")
        return False

    content = CURSORRULES_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    line_count = len(lines)

    print(f"[INFO] .cursorrules: {line_count} lines (target: <= {MAX_LINES})")
    if line_count > MAX_LINES:
        print(f"[WARN] Exceeds {MAX_LINES} line limit by {line_count - MAX_LINES} lines")

    missing = []
    present = []

    for rule_id, rule in ZERO_TOLERANCE_KEYWORDS.items():
        found = any(kw in content for kw in rule["keywords"])
        if found:
            present.append(rule_id)
        else:
            missing.append((rule_id, rule["description"], rule["keywords"]))

    total = len(ZERO_TOLERANCE_KEYWORDS)
    passed = len(present)

    print(f"\n[INFO] Zero-tolerance rule coverage: {passed}/{total}")

    if missing:
        print(f"\n[FAIL] {len(missing)} missing rule(s):")
        for rule_id, desc, keywords in missing:
            print(f"  - {rule_id}: {desc}")
            print(f"    Expected keywords: {keywords}")
    else:
        print("[PASS] All zero-tolerance rules present")

    star_patterns = ["[*]", "[**]", "[***]", "[****]", "[*****]"]
    found_stars = [p for p in star_patterns if p in content]
    if found_stars:
        print(f"\n[WARN] Star-rating markers found: {found_stars}")

    success = len(missing) == 0 and line_count <= MAX_LINES
    if success:
        print(f"\n[PASS] Verification passed ({line_count} lines, {passed}/{total} rules)")
    else:
        print(f"\n[FAIL] Verification failed")

    return success


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
