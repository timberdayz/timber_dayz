#!/usr/bin/env python3
"""Generate the checked-in static baseline from an approved production schema dump."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "current_migrations" / "versions" / "20260805_current_schema_baseline.py"
REVISION = "current_schema_20260805"


def _split_sql_statements(source: str) -> list[str]:
    """Split PostgreSQL DDL without splitting quoted or dollar-quoted bodies."""
    statements: list[str] = []
    start = 0
    index = 0
    quote: str | None = None
    dollar_quote: str | None = None
    while index < len(source):
        char = source[index]
        if dollar_quote:
            if source.startswith(dollar_quote, index):
                index += len(dollar_quote)
                dollar_quote = None
                continue
            index += 1
            continue
        if quote:
            if char == quote:
                if quote == "'" and source[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if source.startswith("--", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            closing = source.find("*/", index + 2)
            index = len(source) if closing == -1 else closing + 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", source[index:])
            if match:
                dollar_quote = match.group(0)
                index += len(dollar_quote)
                continue
        if char == ";":
            statement = source[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1
    trailing = source[start:].strip()
    if trailing:
        statements.append(trailing)
    return statements


def _clean_dump(source: str) -> str:
    """Keep executable PostgreSQL DDL while removing pg_dump client directives."""
    source = source.lstrip("\ufeff")
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("\\"):
            continue
        if stripped.startswith("--"):
            continue
        if re.match(r"^(SET\b|SELECT pg_catalog\.set_config\b)", stripped, re.IGNORECASE):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip() + "\n"
    quarantine_table = re.compile(
        r"(CREATE TABLE core\.data_quarantine \(\s*\n)(.*?)(\n\s*\);)", re.DOTALL
    )

    def remove_retired_columns(match: re.Match[str]) -> str:
        table_body = re.sub(
            r"^\s*(?:platform|data_type)\s+character varying\([^\n]+\),\s*\n",
            "",
            match.group(2),
            flags=re.MULTILINE,
        )
        return match.group(1) + table_body + match.group(3)

    cleaned = quarantine_table.sub(remove_retired_columns, cleaned)
    # Historical Alembic state is an archive concern. Fresh databases must only
    # receive the isolated current-chain version table that Alembic creates.
    def is_archived_or_test_object(statement: str) -> bool:
        normalized = statement.lstrip()
        return bool(
            re.search(r"\b(?:core|public)\.alembic_version(?:\b|__)", normalized)
            or re.match(r"CREATE MATERIALIZED VIEW b_class\.test\b", normalized)
        )

    retained_statements = [
        statement
        for statement in _split_sql_statements(cleaned)
        if not is_archived_or_test_object(statement)
    ]
    return ";\n".join(retained_statements).strip() + "\n"


def generate_baseline_source(dump: str) -> str:
    cleaned = _clean_dump(dump)
    statements = _split_sql_statements(cleaned)
    if "public.sales_targets" in cleaned:
        raise ValueError("approved baseline contains retired public.sales_targets")
    quarantine_match = re.search(
        r"CREATE TABLE core\.data_quarantine \(\s*\n(.*?)\n\s*\);",
        cleaned,
        re.DOTALL,
    )
    if quarantine_match and re.search(
        r"^\s*(platform|data_type)\s+",
        quarantine_match.group(1),
        re.IGNORECASE | re.MULTILINE,
    ):
        raise ValueError("approved baseline contains retired data_quarantine columns")
    return f'''"""Static production schema baseline for the current Alembic chain.

Source: the read-only production schema at legacy revision
20260805_payroll_backfill_audit. The SQL is intentionally frozen here so fresh
databases and approved production adoption use the same reviewed DDL.
"""

from alembic import op

revision = "{REVISION}"
down_revision = None
branch_labels = None
depends_on = None


BASELINE_STATEMENTS = {statements!r}


def upgrade() -> None:
    # psycopg accepts the static pg_dump SQL as one transactional command batch.
    cursor = op.get_bind().connection.driver_connection.cursor()
    try:
        for statement in BASELINE_STATEMENTS:
            cursor.execute(statement)
    finally:
        cursor.close()


def downgrade() -> None:
    raise NotImplementedError("Current production baseline is intentionally non-destructive")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dump", required=True, type=Path)
    args = parser.parse_args()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generate_baseline_source(args.source_dump.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"[OK] Wrote static production baseline: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
