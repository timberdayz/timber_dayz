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


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_execute_refresh_plan_runs_multiple_targets_with_single_run_log(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_refresh_plan
    from backend.services.data_pipeline import refresh_registry

    source_sql = tmp_path / "semantic_source.sql"
    source_sql.write_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW semantic.batch_source AS SELECT 1::int AS value, CURRENT_DATE AS metric_date;\n",
        encoding="utf-8",
    )
    api_sql = tmp_path / "api_view.sql"
    api_sql.write_text(
        "CREATE SCHEMA IF NOT EXISTS api;\n"
        "CREATE OR REPLACE VIEW api.batch_view AS SELECT value, metric_date FROM semantic.batch_source;\n",
        encoding="utf-8",
    )

    source_target = f"semantic.batch_source_{uuid.uuid4().hex[:8]}"
    api_target = f"api.batch_view_{uuid.uuid4().hex[:8]}"

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        original_paths = dict(refresh_registry.SQL_TARGET_PATHS)
        original_dependencies = dict(refresh_registry.PIPELINE_DEPENDENCIES)
        refresh_registry.SQL_TARGET_PATHS[source_target] = str(source_sql)
        refresh_registry.SQL_TARGET_PATHS[api_target] = str(api_sql)
        refresh_registry.PIPELINE_DEPENDENCIES[source_target] = []
        refresh_registry.PIPELINE_DEPENDENCIES[api_target] = [source_target]

        try:
            async with session_factory() as session:
                run_id = await execute_refresh_plan(
                    session,
                    targets=[api_target],
                    pipeline_name="pytest_batch_plan",
                    trigger_source="pytest",
                )
                await session.commit()

                run_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM ops.pipeline_run_log
                            WHERE run_id = :run_id
                            """
                        ),
                        {"run_id": run_id},
                    )
                ).scalar_one()
                assert run_rows == 1

                step_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT target_name, status
                            FROM ops.pipeline_step_log
                            WHERE run_id = :run_id
                            ORDER BY id
                            """
                        ),
                        {"run_id": run_id},
                    )
                ).fetchall()
                assert step_rows == [
                    (source_target, "success"),
                    (api_target, "success"),
                ]
        finally:
            refresh_registry.SQL_TARGET_PATHS.clear()
            refresh_registry.SQL_TARGET_PATHS.update(original_paths)
            refresh_registry.PIPELINE_DEPENDENCIES.clear()
            refresh_registry.PIPELINE_DEPENDENCIES.update(original_dependencies)
            await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_execute_sql_target_retries_and_recovers(monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline import refresh_registry
    from backend.services.data_pipeline import refresh_runner

    sql_path = tmp_path / "retry_target.sql"
    sql_path.write_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW semantic.retry_target AS SELECT 1::int AS value;\n",
        encoding="utf-8",
    )
    target_name = f"semantic.retry_target_{uuid.uuid4().hex[:8]}"

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        original_paths = dict(refresh_registry.SQL_TARGET_PATHS)
        original_dependencies = dict(refresh_registry.PIPELINE_DEPENDENCIES)
        original_execute_sql_file = refresh_runner.execute_sql_file
        refresh_registry.SQL_TARGET_PATHS[target_name] = str(sql_path)
        refresh_registry.PIPELINE_DEPENDENCIES[target_name] = []

        call_count = {"value": 0}

        async def flaky_execute_sql_file(db, path):
            if str(path).endswith("retry_target.sql"):
                call_count["value"] += 1
                if call_count["value"] == 1:
                    raise RuntimeError("transient failure")
            return await original_execute_sql_file(db, path)

        monkeypatch.setattr(refresh_runner, "execute_sql_file", flaky_execute_sql_file)

        try:
            async with session_factory() as session:
                run_id = await refresh_runner.execute_sql_target(
                    session,
                    target_name,
                    pipeline_name="pytest_retry",
                    trigger_source="pytest",
                    max_attempts=2,
                )
                await session.commit()

                assert call_count["value"] == 2

                run_row = (
                    await session.execute(
                        text("SELECT status FROM ops.pipeline_run_log WHERE run_id = :run_id"),
                        {"run_id": run_id},
                    )
                ).scalar_one()
                assert run_row == "success"

                step_row = (
                    await session.execute(
                        text(
                            """
                            SELECT status, details->>'attempts'
                            FROM ops.pipeline_step_log
                            WHERE run_id = :run_id AND target_name = :target_name
                            ORDER BY id DESC
                            LIMIT 1
                            """
                        ),
                        {"run_id": run_id, "target_name": target_name},
                    )
                ).fetchone()
                assert step_row == ("success", "2")
        finally:
            refresh_registry.SQL_TARGET_PATHS.clear()
            refresh_registry.SQL_TARGET_PATHS.update(original_paths)
            refresh_registry.PIPELINE_DEPENDENCIES.clear()
            refresh_registry.PIPELINE_DEPENDENCIES.update(original_dependencies)
            monkeypatch.setattr(refresh_runner, "execute_sql_file", original_execute_sql_file)
            await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_execute_refresh_plan_marks_partial_failed_and_skips_downstream(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline import refresh_registry
    from backend.services.data_pipeline.refresh_runner import execute_refresh_plan

    ok_sql = tmp_path / "ok.sql"
    ok_sql.write_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW semantic.ok_target AS SELECT 1::int AS value;\n",
        encoding="utf-8",
    )
    bad_sql = tmp_path / "bad.sql"
    bad_sql.write_text("THIS IS INVALID SQL;\n", encoding="utf-8")
    downstream_sql = tmp_path / "downstream.sql"
    downstream_sql.write_text(
        "CREATE SCHEMA IF NOT EXISTS api;\n"
        "CREATE OR REPLACE VIEW api.downstream_target AS SELECT 1::int AS value;\n",
        encoding="utf-8",
    )

    ok_target = f"semantic.ok_target_{uuid.uuid4().hex[:8]}"
    bad_target = f"semantic.bad_target_{uuid.uuid4().hex[:8]}"
    downstream_target = f"api.downstream_target_{uuid.uuid4().hex[:8]}"

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        original_paths = dict(refresh_registry.SQL_TARGET_PATHS)
        original_dependencies = dict(refresh_registry.PIPELINE_DEPENDENCIES)
        refresh_registry.SQL_TARGET_PATHS[ok_target] = str(ok_sql)
        refresh_registry.SQL_TARGET_PATHS[bad_target] = str(bad_sql)
        refresh_registry.SQL_TARGET_PATHS[downstream_target] = str(downstream_sql)
        refresh_registry.PIPELINE_DEPENDENCIES[ok_target] = []
        refresh_registry.PIPELINE_DEPENDENCIES[bad_target] = [ok_target]
        refresh_registry.PIPELINE_DEPENDENCIES[downstream_target] = [bad_target]

        try:
            async with session_factory() as session:
                run_id = await execute_refresh_plan(
                    session,
                    targets=[downstream_target],
                    pipeline_name="pytest_partial_failure",
                    trigger_source="pytest",
                    continue_on_error=True,
                    max_attempts=1,
                )
                await session.commit()

                run_status = (
                    await session.execute(
                        text("SELECT status FROM ops.pipeline_run_log WHERE run_id = :run_id"),
                        {"run_id": run_id},
                    )
                ).scalar_one()
                assert run_status == "partial_failed"

                step_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT target_name, status
                            FROM ops.pipeline_step_log
                            WHERE run_id = :run_id
                            ORDER BY id
                            """
                        ),
                        {"run_id": run_id},
                    )
                ).fetchall()
                assert step_rows == [
                    (ok_target, "success"),
                    (bad_target, "failed"),
                    (downstream_target, "skipped"),
                ]
        finally:
            refresh_registry.SQL_TARGET_PATHS.clear()
            refresh_registry.SQL_TARGET_PATHS.update(original_paths)
            refresh_registry.PIPELINE_DEPENDENCIES.clear()
            refresh_registry.PIPELINE_DEPENDENCIES.update(original_dependencies)
            await engine.dispose()
