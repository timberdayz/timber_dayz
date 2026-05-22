#!/usr/bin/env python3
"""Verify architecture single-source-of-truth constraints."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "backups",
    "migration_temp",
    "node_modules",
    "temp",
    "venv",
}

ALLOWED_LEGACY_FILES = {
    PROJECT_ROOT / "modules" / "utils" / "sessions" / "legacy_shop_artifact_cleanup.py",
}


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("gbk", errors="ignore").decode("gbk"))


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def find_base_definitions() -> list[tuple[Path, int]]:
    base_definitions: list[tuple[Path, int]] = []

    for py_file in PROJECT_ROOT.rglob("*.py"):
        if is_excluded(py_file) or py_file.name == Path(__file__).name:
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if "declarative_base()" not in content:
            continue

        for line_number, line in enumerate(content.splitlines(), 1):
            if "declarative_base()" in line and not line.strip().startswith("#"):
                base_definitions.append((py_file, line_number))

    return base_definitions


def find_duplicate_models() -> list[str]:
    models: dict[str, Path] = {}
    duplicates: list[str] = []

    for py_file in PROJECT_ROOT.rglob("*.py"):
        if is_excluded(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            for item in node.body:
                if not isinstance(item, ast.Assign):
                    continue

                for target in item.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__tablename__"
                        and isinstance(item.value, ast.Constant)
                    ):
                        table_name = item.value.value
                        if table_name in models:
                            duplicates.append(
                                f"{table_name}: {models[table_name]} AND {py_file}"
                            )
                        else:
                            models[table_name] = py_file

    return duplicates


def find_unarchived_legacy_files() -> list[Path]:
    legacy_patterns = ["**/legacy_*", "**/*_old.*", "**/*_backup.*"]
    legacy_files: list[Path] = []

    for pattern in legacy_patterns:
        for file_path in PROJECT_ROOT.glob(pattern):
            if is_excluded(file_path):
                continue
            if file_path in ALLOWED_LEGACY_FILES:
                continue
            if file_path.is_file():
                legacy_files.append(file_path)

    return legacy_files


def main() -> int:
    safe_print("\n" + "=" * 80)
    safe_print("Architecture SSOT Verification - Enterprise ERP Standard")
    safe_print("=" * 80)

    passed = 0
    failed = 0

    safe_print("\n[Test 1] Checking Base = declarative_base() definitions...")
    safe_print("-" * 80)

    allowed_base = PROJECT_ROOT / "modules" / "core" / "db" / "schema.py"
    violations = [
        base_definition
        for base_definition in find_base_definitions()
        if base_definition[0] != allowed_base
    ]

    if not violations:
        safe_print(f"  [PASS] Only 1 Base definition found in: {allowed_base}")
        passed += 1
    else:
        safe_print(f"  [FAIL] Found {len(violations) + 1} Base definitions:")
        safe_print(f"    [OK] {allowed_base} - Correct location")
        for file_path, line_number in violations:
            safe_print(
                f"    [ERROR] {file_path.relative_to(PROJECT_ROOT)} "
                f"(line {line_number}) - DUPLICATE"
            )
        failed += 1

    safe_print("\n[Test 2] Checking for duplicate ORM model definitions...")
    safe_print("-" * 80)

    duplicates = find_duplicate_models()
    if not duplicates:
        safe_print("  [PASS] No duplicate model definitions found")
        passed += 1
    else:
        safe_print(f"  [FAIL] Found {len(duplicates)} duplicate models:")
        for duplicate in duplicates:
            safe_print(f"    [ERROR] {duplicate}")
        failed += 1

    safe_print("\n[Test 3] Checking critical architecture files...")
    safe_print("-" * 80)

    critical_files = [
        ("modules/core/db/schema.py", "Core ORM schema"),
        ("modules/core/db/__init__.py", "Core DB exports"),
        ("backend/models/database.py", "Backend DB connector"),
        ("AGENTS.md", "Repository rules"),
    ]
    missing = []

    for file_path, description in critical_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            safe_print(f"  [OK] {file_path} ({description})")
        else:
            safe_print(f"  [ERROR] {file_path} ({description}) - MISSING")
            missing.append(file_path)

    if not missing:
        passed += 1
    else:
        failed += 1

    safe_print("\n[Test 4] Checking for unarchived legacy files...")
    safe_print("-" * 80)

    legacy_files = find_unarchived_legacy_files()
    if not legacy_files:
        safe_print("  [PASS] No unarchived legacy files found")
        passed += 1
    else:
        safe_print(f"  [FAIL] Found {len(legacy_files)} unarchived legacy files:")
        for file_path in legacy_files:
            safe_print(f"    {file_path.relative_to(PROJECT_ROOT)}")
        failed += 1

    safe_print("\n" + "=" * 80)
    safe_print("Verification Summary")
    safe_print("=" * 80)
    safe_print(f"  PASSED: {passed}")
    safe_print(f"  FAILED: {failed}")
    safe_print(f"  TOTAL:  {passed + failed}")

    success_rate = passed / (passed + failed) * 100 if (passed + failed) else 0
    safe_print(f"\n  Compliance Rate: {success_rate:.1f}%")

    if failed == 0:
        safe_print("\n[OK] Architecture complies with Enterprise ERP SSOT standard")
        safe_print("=" * 80)
        return 0

    safe_print(f"\n[ERROR] {failed} violation(s) found. Please review and fix.")
    safe_print("=" * 80)
    return 1


if __name__ == "__main__":
    sys.exit(main())
