#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only inspection for the operating_costs schema contract."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine, text


COLUMN_SQL = text(
    """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'a_class'
      AND table_name = 'operating_costs'
      AND column_name IN ('营销费用', '工资', 'marketing_fee', 'salary')
    ORDER BY column_name
    """
)

DEPENDENCY_SQL = text(
    """
    SELECT DISTINCT
        n.nspname AS schema_name,
        c.relname AS object_name,
        c.relkind AS object_kind
    FROM pg_attribute a
    JOIN pg_class t
      ON t.oid = a.attrelid
    JOIN pg_namespace tn
      ON tn.oid = t.relnamespace
    JOIN pg_depend d
      ON d.refobjid = a.attrelid
     AND d.refobjsubid = a.attnum
    JOIN pg_rewrite r
      ON r.oid = d.objid
    JOIN pg_class c
      ON c.oid = r.ev_class
    JOIN pg_namespace n
      ON n.oid = c.relnamespace
    WHERE tn.nspname = 'a_class'
      AND t.relname = 'operating_costs'
      AND a.attname IN ('营销费用', '工资', 'marketing_fee', 'salary')
    ORDER BY schema_name, object_name
    """
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect operating_costs schema compatibility")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only.",
    )
    return parser.parse_args()


def inspect_schema(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        columns = [row[0] for row in conn.execute(COLUMN_SQL).fetchall()]
        dependencies = [
            {
                "schema": row[0],
                "object_name": row[1],
                "object_kind": row[2],
            }
            for row in conn.execute(DEPENDENCY_SQL).fetchall()
        ]

    return {
        "operating_costs_columns": columns,
        "legacy_columns_present": [name for name in columns if name in {"工资", "salary"}],
        "current_columns_present": [name for name in columns if name in {"营销费用", "marketing_fee"}],
        "dependent_objects": dependencies,
    }


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required. Pass --database-url or set DATABASE_URL.")

    payload = inspect_schema(args.database_url)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("[INFO] operating_costs compatibility inspection")
    print(f"[INFO] Current columns: {payload['current_columns_present']}")
    print(f"[INFO] Legacy columns: {payload['legacy_columns_present']}")
    if payload["dependent_objects"]:
        print("[INFO] Dependent objects touching inspected columns:")
        for item in payload["dependent_objects"]:
            print(f"  - {item['schema']}.{item['object_name']} ({item['object_kind']})")
    else:
        print("[INFO] No dependent views/materialized views found for inspected columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
