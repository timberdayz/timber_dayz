#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verify hygiene rules for dashboard SQL assets.

This is a fast, no-DB check intended to prevent corrupted SQL from breaking bootstrap/startup.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_ROOT = ROOT / "sql"


DEFAULT_ALLOW_DYNAMIC: set[str] = set()


_REPLACEMENT_CHAR = "\ufffd"
_NUL_BYTE = "\x00"
_DYNAMIC_SQL_RE = re.compile(r"(?is)\bDO\s+\$[A-Za-z_0-9]+\$.*?\bEXECUTE\b")
_QUOTED_IDENT_WITH_QUESTION_RE = re.compile(r'"[^"\n\r]*[?\ufffd][^"\n\r]*"')
_JSON_KEY_WITH_QUESTION_RE = re.compile(r"(?is)->>\s*'[^'\n\r]*[?\ufffd][^'\n\r]*'")


def _iter_sql_files() -> list[Path]:
    if not SQL_ROOT.exists():
        return []
    roots = [SQL_ROOT / "semantic", SQL_ROOT / "mart", SQL_ROOT / "api_modules"]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend([p for p in root.rglob("*.sql") if p.is_file()])
    return sorted(files, key=lambda p: str(p).lower())


def _read_text_utf8(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("contains NUL byte(s)")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"not valid UTF-8: {exc}") from exc
    if _REPLACEMENT_CHAR in text:
        raise ValueError("contains Unicode replacement character (�)")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify SQL asset hygiene")
    parser.add_argument(
        "--allow-dynamic",
        action="append",
        default=[],
        help="Allow dynamic SQL patterns for this path (repeatable, relative to repo root).",
    )
    args = parser.parse_args(argv)

    allow_dynamic = set(DEFAULT_ALLOW_DYNAMIC)
    for rel in args.allow_dynamic:
        allow_dynamic.add(str((ROOT / rel).resolve()).lower())

    failures: list[str] = []
    for path in _iter_sql_files():
        rel = path.relative_to(ROOT)
        try:
            text = _read_text_utf8(path)
        except Exception as exc:
            failures.append(f"{rel}: {exc}")
            continue

        if _QUOTED_IDENT_WITH_QUESTION_RE.search(text):
            failures.append(f"{rel}: suspicious quoted identifier contains '?' or '�'")

        if _JSON_KEY_WITH_QUESTION_RE.search(text):
            failures.append(f"{rel}: suspicious JSON key contains '?' or '�'")

        if _DYNAMIC_SQL_RE.search(text):
            if str(path.resolve()).lower() not in allow_dynamic:
                failures.append(f"{rel}: contains dynamic SQL (DO ... EXECUTE ...) but is not allowlisted")

    if failures:
        print("SQL asset hygiene check failed:")
        for item in failures:
            print(f"- {item}")
        print("\nFix the SQL file(s) or update the allowlist only after review.")
        return 1

    print("SQL asset hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
