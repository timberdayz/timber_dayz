#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quick ops checker for PostgreSQL dashboard rollout.

Reads recent records from:
- ops.pipeline_run_log
- ops.pipeline_step_log
- ops.data_freshness_log
- ops.data_lineage_registry
"""

from __future__ import annotations

import asyncio
from sqlalchemy import text

from backend.models.database import AsyncSessionLocal


async def main() -> int:
    async with AsyncSessionLocal() as session:
        checks = {
            "pipeline_run_log": """
                SELECT run_id, pipeline_name, status, started_at, completed_at
                FROM ops.pipeline_run_log
                ORDER BY id DESC
                LIMIT 5
            """,
            "pipeline_step_log": """
                SELECT run_id, target_name, status, completed_at
                FROM ops.pipeline_step_log
                ORDER BY id DESC
                LIMIT 10
            """,
            "data_freshness_log": """
                SELECT target_name, target_type, status, last_succeeded_at
                FROM ops.data_freshness_log
                ORDER BY target_name
                LIMIT 20
            """,
            "data_lineage_registry": """
                SELECT target_name, source_name, source_type, dependency_level
                FROM ops.data_lineage_registry
                WHERE active = TRUE
                ORDER BY target_name, dependency_level, source_name
                LIMIT 20
            """,
        }

        for name, sql in checks.items():
            print(f"=== {name} ===")
            result = await session.execute(text(sql))
            rows = result.fetchall()
            if not rows:
                print("(no rows)")
                continue
            for row in rows:
                print(dict(row._mapping))
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
