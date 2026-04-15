#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check timestamp default drift between ORM metadata and PostgreSQL tables.

This script scans ORM columns named created_at / updated_at that declare a
server_default, then compares them with the live database column_default.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def expected_timestamp_columns():
    from modules.core.db import Base

    rows = []
    for table in Base.metadata.tables.values():
        schema_name = table.schema or "public"
        for column in table.columns:
            if column.name not in {"created_at", "updated_at"}:
                continue
            if column.server_default is None:
                continue
            rows.append(
                {
                    "schema": schema_name,
                    "table": table.name,
                    "column": column.name,
                }
            )
    return rows


def fetch_actual_defaults(connection, schema_name: str, table_name: str) -> dict[str, str | None]:
    result = connection.execute(
        text(
            """
            SELECT column_name, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name IN ('created_at', 'updated_at')
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return {row[0]: row[1] for row in result}


def is_expected_timestamp_default(default_value: str | None) -> bool:
    if default_value is None:
        return False
    normalized = default_value.lower()
    return "now()" in normalized or "current_timestamp" in normalized


def main() -> int:
    from backend.utils.config import get_settings

    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        print("[SKIP] SQLite: timestamp default drift audit supports PostgreSQL only.")
        return 0

    engine = create_engine(url, pool_pre_ping=True)
    mismatches = []
    try:
        with engine.connect() as connection:
            for row in expected_timestamp_columns():
                actual_defaults = fetch_actual_defaults(connection, row["schema"], row["table"])
                actual_default = actual_defaults.get(row["column"])
                if not is_expected_timestamp_default(actual_default):
                    mismatches.append(
                        {
                            "schema": row["schema"],
                            "table": row["table"],
                            "column": row["column"],
                            "actual_default": actual_default,
                        }
                    )
    finally:
        engine.dispose()

    if not mismatches:
        print("[OK] No timestamp default drift detected.")
        return 0

    print("[FAIL] Timestamp default drift detected:")
    for item in mismatches:
        print(
            f"- {item['schema']}.{item['table']}.{item['column']}: "
            f"column_default={item['actual_default']!r}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
