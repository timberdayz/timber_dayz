from pathlib import Path
import uuid

import pytest
from sqlalchemy import text


def test_sql_loader_reads_sql_file_text():
    from backend.services.data_pipeline.sql_loader import load_sql_text

    sql_text = load_sql_text(Path("sql/ops/create_pipeline_tables.sql"))
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql_text


def test_split_sql_statements_handles_multiple_create_statements():
    from backend.services.data_pipeline.sql_loader import split_sql_statements

    statements = split_sql_statements(
        """
        CREATE SCHEMA IF NOT EXISTS ops;
        CREATE TABLE IF NOT EXISTS ops.example_a (id BIGINT);
        CREATE TABLE IF NOT EXISTS ops.example_b (id BIGINT);
        """
    )

    assert statements == [
        "CREATE SCHEMA IF NOT EXISTS ops",
        "CREATE TABLE IF NOT EXISTS ops.example_a (id BIGINT)",
        "CREATE TABLE IF NOT EXISTS ops.example_b (id BIGINT)",
    ]


def test_refresh_registry_exposes_dependency_order():
    from backend.services.data_pipeline.refresh_registry import (
        PIPELINE_DEPENDENCIES,
        SQL_TARGET_PATHS,
        topologically_sort_targets,
    )

    assert PIPELINE_DEPENDENCIES["semantic.fact_orders_atomic"] == []
    assert SQL_TARGET_PATHS["semantic.fact_orders_atomic"] == "sql/semantic/orders_atomic.sql"
    assert SQL_TARGET_PATHS["api.business_overview_kpi_module"] == "sql/api_modules/business_overview_kpi_module.sql"
    ordered = topologically_sort_targets(
        [
            "api.business_overview_kpi_module",
            "mart.shop_month_kpi",
            "semantic.fact_orders_atomic",
            "semantic.fact_analytics_atomic",
        ]
    )
    assert ordered.index("semantic.fact_orders_atomic") < ordered.index("mart.shop_month_kpi")
    assert ordered.index("semantic.fact_analytics_atomic") < ordered.index("mart.shop_month_kpi")
    assert ordered.index("mart.shop_month_kpi") < ordered.index("api.business_overview_kpi_module")


def test_refresh_runner_builds_step_plan():
    from backend.services.data_pipeline.refresh_runner import build_refresh_plan

    plan = build_refresh_plan(["api.business_overview_kpi_module"])
    assert plan == [
        "semantic.fact_orders_atomic",
        "semantic.fact_analytics_atomic",
        "mart.shop_month_kpi",
        "api.business_overview_kpi_module",
    ]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_execute_sql_target_creates_ops_tables():
    from backend.services.data_pipeline.refresh_runner import execute_sql_target
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await execute_sql_target(session, "ops.pipeline_run_log")
            await session.commit()

            result = await session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'ops'
                      AND table_name IN (
                          'pipeline_run_log',
                          'pipeline_step_log',
                          'data_freshness_log',
                          'data_lineage_registry'
                      )
                    ORDER BY table_name
                    """
                )
            )
            assert [row[0] for row in result.fetchall()] == [
                "data_freshness_log",
                "data_lineage_registry",
                "pipeline_run_log",
                "pipeline_step_log",
            ]

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_execute_sql_target_records_pipeline_metadata(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target
    from backend.services.data_pipeline import refresh_registry

    sql_path = tmp_path / "fake_target.sql"
    sql_path.write_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW semantic.fake_target AS SELECT 1::int AS value, CURRENT_DATE AS metric_date;\n",
        encoding="utf-8",
    )

    target_name = f"semantic.fake_target_{uuid.uuid4().hex[:8]}"

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        original_paths = dict(refresh_registry.SQL_TARGET_PATHS)
        original_dependencies = dict(refresh_registry.PIPELINE_DEPENDENCIES)
        refresh_registry.SQL_TARGET_PATHS[target_name] = str(sql_path)
        refresh_registry.PIPELINE_DEPENDENCIES[target_name] = ["semantic.fact_orders_atomic"]

        try:
            async with session_factory() as session:
                await execute_sql_target(
                    session,
                    target_name,
                    pipeline_name="pytest_pipeline",
                    trigger_source="pytest",
                )
                await session.commit()

                run_row = (
                    await session.execute(
                        text(
                            """
                            SELECT pipeline_name, status, trigger_source
                            FROM ops.pipeline_run_log
                            ORDER BY id DESC
                            LIMIT 1
                            """
                        )
                    )
                ).fetchone()
                assert run_row == ("pytest_pipeline", "success", "pytest")

                step_row = (
                    await session.execute(
                        text(
                            """
                            SELECT target_name, status
                            FROM ops.pipeline_step_log
                            ORDER BY id DESC
                            LIMIT 1
                            """
                        )
                    )
                ).fetchone()
                assert step_row == (target_name, "success")

                freshness_row = (
                    await session.execute(
                        text(
                            """
                            SELECT target_name, target_type, status
                            FROM ops.data_freshness_log
                            WHERE target_name = :target_name
                            """
                        ),
                        {"target_name": target_name},
                    )
                ).fetchone()
                assert freshness_row == (target_name, "semantic", "success")

                lineage_row = (
                    await session.execute(
                        text(
                            """
                            SELECT target_name, source_name, source_type
                            FROM ops.data_lineage_registry
                            WHERE target_name = :target_name
                            ORDER BY id DESC
                            LIMIT 1
                            """
                        ),
                        {"target_name": target_name},
                    )
                ).fetchone()
                assert lineage_row == (target_name, "semantic.fact_orders_atomic", "semantic")
        finally:
            refresh_registry.SQL_TARGET_PATHS.clear()
            refresh_registry.SQL_TARGET_PATHS.update(original_paths)
            refresh_registry.PIPELINE_DEPENDENCIES.clear()
            refresh_registry.PIPELINE_DEPENDENCIES.update(original_dependencies)
            await engine.dispose()
