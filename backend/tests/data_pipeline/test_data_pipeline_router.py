import json

import pytest
from sqlalchemy import text


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_data_pipeline_status_route_reads_latest_runs():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.routers.data_pipeline import get_pipeline_status
    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await execute_sql_target(
                session,
                "ops.pipeline_run_log",
                pipeline_name="router_status_test",
                trigger_source="pytest",
            )
            await session.commit()

            response = await get_pipeline_status(db=session)
            body = json.loads(response.body.decode("utf-8"))

            assert body["success"] is True
            assert body["data"]["runs"][0]["pipeline_name"] == "router_status_test"
            assert body["data"]["runs"][0]["status"] == "success"

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_data_pipeline_freshness_and_lineage_routes_read_rows(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.routers.data_pipeline import get_pipeline_freshness, get_pipeline_lineage
    from backend.services.data_pipeline import refresh_registry
    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    sql_path = tmp_path / "router_target.sql"
    sql_path.write_text(
        "CREATE SCHEMA IF NOT EXISTS semantic;\n"
        "CREATE OR REPLACE VIEW semantic.router_target AS SELECT 1::int AS value, CURRENT_DATE AS metric_date;\n",
        encoding="utf-8",
    )
    target_name = "semantic.router_target"

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
                    pipeline_name="router_freshness_test",
                    trigger_source="pytest",
                )
                await session.commit()

                freshness_response = await get_pipeline_freshness(db=session)
                freshness_body = json.loads(freshness_response.body.decode("utf-8"))
                assert freshness_body["success"] is True
                assert freshness_body["data"]["targets"][0]["target_name"] == target_name
                assert freshness_body["data"]["targets"][0]["status"] == "success"

                lineage_response = await get_pipeline_lineage(db=session)
                lineage_body = json.loads(lineage_response.body.decode("utf-8"))
                assert lineage_body["success"] is True
                assert lineage_body["data"]["edges"][0]["target_name"] == target_name
                assert lineage_body["data"]["edges"][0]["source_name"] == "semantic.fact_orders_atomic"
        finally:
            refresh_registry.SQL_TARGET_PATHS.clear()
            refresh_registry.SQL_TARGET_PATHS.update(original_paths)
            refresh_registry.PIPELINE_DEPENDENCIES.clear()
            refresh_registry.PIPELINE_DEPENDENCIES.update(original_dependencies)
            await engine.dispose()
