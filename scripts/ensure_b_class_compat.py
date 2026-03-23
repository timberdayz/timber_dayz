#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy import text

from backend.models.database import AsyncSessionLocal


ROOT_DIR = Path(__file__).resolve().parent.parent
SEMANTIC_DIR = ROOT_DIR / "sql" / "semantic"

DEFAULT_RAW_TABLE_COLUMNS = [
    "id BIGSERIAL PRIMARY KEY",
    "platform_code VARCHAR(32) NOT NULL",
    "shop_id VARCHAR(256)",
    "data_domain VARCHAR(64) NOT NULL",
    "granularity VARCHAR(32) NOT NULL",
    "sub_domain VARCHAR(64)",
    "metric_date DATE NOT NULL",
    "period_start_date DATE",
    "period_end_date DATE",
    "period_start_time TIMESTAMP",
    "period_end_time TIMESTAMP",
    "file_id INTEGER",
    "template_id INTEGER",
    "raw_data JSONB NOT NULL",
    "header_columns JSONB",
    "data_hash VARCHAR(64) NOT NULL",
    "ingest_timestamp TIMESTAMP NOT NULL DEFAULT NOW()",
    "currency_code VARCHAR(3)",
]


def extract_b_class_table_names(sql_text: str) -> set[str]:
    pattern = re.compile(r"b_class\.([A-Za-z0-9_]+)")
    return set(pattern.findall(sql_text))


def collect_required_b_class_tables() -> set[str]:
    tables: set[str] = set()
    for path in SEMANTIC_DIR.glob("*.sql"):
        tables.update(extract_b_class_table_names(path.read_text(encoding="utf-8", errors="replace")))
    return tables


async def ensure_b_class_compatibility() -> list[str]:
    actions: list[str] = []
    required_tables = sorted(collect_required_b_class_tables())

    async with AsyncSessionLocal() as session:
        await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))

        result = await session.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'b_class_canonical'
                """
            )
        )
        canonical_tables = {row[0] for row in result.fetchall()}

        result = await session.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'b_class'
                UNION
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'b_class'
                """
            )
        )
        existing_b_class = {row[0] for row in result.fetchall()}

        for table_name in required_tables:
            if table_name in existing_b_class:
                actions.append(f"keep:{table_name}")
                continue

            if table_name in canonical_tables:
                await session.execute(
                    text(
                        f'CREATE OR REPLACE VIEW b_class."{table_name}" AS '
                        f'SELECT * FROM b_class_canonical."{table_name}"'
                    )
                )
                actions.append(f"view:{table_name}")
                continue

            create_sql = (
                f'CREATE TABLE IF NOT EXISTS b_class."{table_name}" (\n  '
                + ",\n  ".join(DEFAULT_RAW_TABLE_COLUMNS)
                + "\n)"
            )
            await session.execute(text(create_sql))
            actions.append(f"table:{table_name}")

        await session.commit()

    return actions


async def main() -> int:
    actions = await ensure_b_class_compatibility()
    for action in actions:
        print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
