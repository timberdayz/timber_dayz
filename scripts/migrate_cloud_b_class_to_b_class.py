#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Migrate cloud mirror rows from cloud_b_class.fact_* into b_class.fact_*."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.services.cloud_b_class_mirror_manager import (  # noqa: E402
    CloudBClassMirrorManager,
    build_canonical_columns,
)
from backend.services.cloud_b_class_sync_service import CloudBClassSyncService  # noqa: E402
from backend.services.data_pipeline.refresh_runner import execute_refresh_plan  # noqa: E402
from backend.models.database import get_async_database_url  # noqa: E402
from backend.utils.project_env import load_project_env  # noqa: E402


REFRESH_TARGETS = [
    "api.business_overview_kpi_module",
    "api.business_overview_comparison_module",
    "api.business_overview_shop_racing_module",
    "api.business_overview_traffic_ranking_module",
    "api.business_overview_operational_metrics_module",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate cloud_b_class fact tables into b_class and refresh dashboard assets"
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--skip-refresh", action="store_true")
    return parser.parse_args(argv)


def _build_upsert_sql(table_name: str, data_domain: str) -> str:
    columns = build_canonical_columns()
    column_list = ", ".join(columns)
    select_columns = []
    for column in columns:
        if column in {"file_id", "template_id"}:
            select_columns.append(f"NULL AS {column}")
        else:
            select_columns.append(column)
    select_list = ", ".join(select_columns)
    update_fields = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in columns
        if column not in {"platform_code", "shop_id", "data_domain", "granularity", "sub_domain", "data_hash"}
    )
    conflict_clause = CloudBClassSyncService._infer_data_domain(table_name)
    if conflict_clause == "services":
        conflict_columns = "(data_domain, sub_domain, granularity, data_hash)"
    else:
        conflict_columns = "(platform_code, shop_id, data_domain, granularity, data_hash)"
    return (
        f'INSERT INTO b_class."{table_name}" ({column_list}) '
        f'SELECT {select_list} FROM cloud_b_class."{table_name}" '
        f"ON CONFLICT {conflict_columns} DO UPDATE SET {update_fields}"
    )


def migrate_tables(database_url: str) -> tuple[list[str], list[str]]:
    engine = create_engine(database_url)
    migrated_tables: list[str] = []
    skipped_tables: list[str] = []
    try:
        table_names = sorted(
            name
            for name in inspect(engine).get_table_names(schema="cloud_b_class")
            if name.startswith("fact_")
        )
        manager = CloudBClassMirrorManager(engine, schema_name="b_class")
        with engine.begin() as conn:
            for table_name in table_names:
                data_domain = CloudBClassSyncService._infer_data_domain(table_name)
                try:
                    manager.ensure_cloud_mirror_table(table_name, data_domain)
                except RuntimeError as exc:
                    skipped_tables.append(f"{table_name}: {exc}")
                    continue
                conn.execute(text(_build_upsert_sql(table_name, data_domain)))
                migrated_tables.append(table_name)
        return migrated_tables, skipped_tables
    finally:
        engine.dispose()


async def refresh_dashboard_assets(database_url: str) -> dict:
    async_engine = create_async_engine(get_async_database_url(database_url))
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await execute_refresh_plan(
                session,
                targets=REFRESH_TARGETS,
                pipeline_name="cloud_b_class_to_b_class_migration_refresh",
                trigger_source="cloud_b_class_to_b_class_migration",
                context={"source_schema": "cloud_b_class", "target_schema": "b_class"},
                continue_on_error=False,
            )
            await session.commit()
            return result
    finally:
        await async_engine.dispose()


def main(argv: list[str] | None = None) -> int:
    load_project_env(project_root, profile="collection")
    args = parse_args(argv)
    database_url = args.database_url
    if not database_url:
        database_url = __import__("os").getenv("CLOUD_DATABASE_URL")
    if not database_url:
        raise RuntimeError("CLOUD_DATABASE_URL is required")

    migrated_tables, skipped_tables = migrate_tables(database_url)
    print(f"migrated_tables={len(migrated_tables)}")
    if skipped_tables:
        print(f"skipped_tables={len(skipped_tables)}")
        for item in skipped_tables:
            print(item)
    if not args.skip_refresh:
        result = asyncio.run(refresh_dashboard_assets(database_url))
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
