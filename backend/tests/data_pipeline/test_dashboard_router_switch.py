import importlib
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def test_environment_examples_document_dashboard_router_flags():
    for path_str in (".env.example", "env.development.example", "env.production.example"):
        text = Path(path_str).read_text(encoding="utf-8")
        assert "USE_POSTGRESQL_DASHBOARD_ROUTER=" in text


def test_rollout_doc_covers_enable_verify_and_rollback():
    text = Path("docs/development/POSTGRESQL_DASHBOARD_ROLLOUT.md").read_text(encoding="utf-8")
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER=true" in text
    assert "ops.pipeline_run_log" in text
    assert "回退" in text


@pytest_asyncio.fixture
async def switched_app(monkeypatch):
    import backend.main as main_module

    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
    reloaded = importlib.reload(main_module)
    yield reloaded.app
    monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
    importlib.reload(main_module)


@pytest.mark.asyncio
async def test_main_switches_to_postgresql_dashboard_router(switched_app, monkeypatch):
    class _PostgresqlServiceStub:
        async def get_business_overview_kpi(self, month, platform):
            return {
                "gmv": 321,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 32.1,
                "attach_rate": 1.5,
                "labor_efficiency": 0,
            }

        async def get_business_overview_shop_racing(self, granularity, target_date, group_by):
            return [{"name": "shop-a", "gmv": 123, "rank": 1}]

        async def get_business_overview_operational_metrics(self, month, platform):
            return {
                "monthly_target": 1000,
                "monthly_total_achieved": 800,
                "estimated_expenses": 300,
                "operating_result_text": "盈利",
            }

        async def get_annual_summary_target_completion(self, db, granularity, period):
            return {
                "target_gmv": 1000,
                "achieved_gmv": 800,
                "achievement_rate_gmv": 80.0,
                "target_orders": 80,
                "target_profit": None,
                "achieved_profit": 120,
                "achievement_rate_profit": None,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _PostgresqlServiceStub(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=switched_app),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/api/dashboard/business-overview/kpi", params={"month": "2026-03-01"})

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["data"]["gmv"] == 321

    async with AsyncClient(
        transport=ASGITransport(app=switched_app),
        base_url="http://localhost",
    ) as client:
        shop_racing = await client.get(
            "/api/dashboard/business-overview/shop-racing",
            params={"granularity": "monthly", "date": "2026-03-01", "group_by": "shop"},
        )
        operational = await client.get(
            "/api/dashboard/business-overview/operational-metrics",
            params={"month": "2026-03-01"},
        )
        target_completion = await client.get(
            "/api/dashboard/annual-summary/target-completion",
            params={"granularity": "yearly", "period": "2026"},
        )

    shop_body = json.loads(shop_racing.content.decode("utf-8"))
    operational_body = json.loads(operational.content.decode("utf-8"))
    target_completion_body = json.loads(target_completion.content.decode("utf-8"))
    assert shop_racing.status_code == 200
    assert shop_body["data"][0]["rank"] == 1
    assert operational.status_code == 200
    assert operational_body["data"]["operating_result_text"] == "盈利"
    assert target_completion.status_code == 200
    assert target_completion_body["data"]["achievement_rate_gmv"] == 80.0


def test_main_contains_explicit_dashboard_router_source_log():
    text = Path("backend/main.py").read_text(encoding="utf-8")
    assert "Dashboard router source: PostgreSQL" in text
    assert "Dashboard router source: Metabase compatibility" not in text


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_switched_app_serves_real_postgresql_dashboard_routes(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.models.database import get_async_db

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS api"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_comparison_module AS
                    SELECT
                        'monthly'::varchar AS granularity,
                        DATE '2026-03-01' AS period_start,
                        DATE '2026-03-31' AS period_end,
                        DATE '2026-03-01' AS period_key,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        321::numeric AS sales_amount,
                        10::numeric AS sales_quantity,
                        200::numeric AS traffic,
                        5::numeric AS conversion_rate,
                        32.1::numeric AS avg_order_value,
                        1.5::numeric AS attach_rate,
                        120::numeric AS profit,
                        400::numeric AS target_sales_amount,
                        12::numeric AS target_sales_quantity
                    UNION ALL
                    SELECT
                        'monthly', DATE '2026-02-01', DATE '2026-02-28', DATE '2026-02-01',
                        'shopee', 'shop-a', 300, 9, 180, 5, 33.3, 1.4, 100, 0, 0
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS
                    SELECT
                        'monthly'::varchar AS granularity,
                        DATE '2026-03-01' AS period_key,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        321::numeric AS gmv,
                        10::numeric AS order_count,
                        32.1::numeric AS avg_order_value,
                        1.5::numeric AS attach_rate,
                        120::numeric AS profit
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
                    SELECT
                        DATE '2026-03-01' AS period_month,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        1000::numeric AS monthly_target,
                        800::numeric AS monthly_total_achieved,
                        120::numeric AS today_sales,
                        80::numeric AS monthly_achievement_rate,
                        0::numeric AS time_gap,
                        200::numeric AS estimated_gross_profit,
                        300::numeric AS estimated_expenses,
                        -100::numeric AS operating_result,
                        '亏损'::varchar AS operating_result_text,
                        10::numeric AS monthly_order_count,
                        10::numeric AS today_order_count
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.business_overview_kpi_module AS
                    SELECT
                        DATE '2026-03-01' AS period_month,
                        'shopee'::varchar AS platform_code,
                        321::numeric AS gmv,
                        10::numeric AS order_count,
                        200::numeric AS visitor_count,
                        5::numeric AS conversion_rate,
                        32.1::numeric AS avg_order_value,
                        1.5::numeric AS attach_rate,
                        15::numeric AS total_items,
                        120::numeric AS profit
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.annual_summary_kpi_module AS
                    SELECT
                        DATE '2026-01-01' AS period_month,
                        800::numeric AS gmv,
                        300::numeric AS total_cost,
                        120::numeric AS profit,
                        15::numeric AS gross_margin,
                        -22.5::numeric AS net_margin,
                        -0.6::numeric AS roi
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.annual_summary_trend_module AS
                    SELECT
                        DATE '2026-01-01' AS period_month,
                        800::numeric AS gmv,
                        300::numeric AS total_cost,
                        120::numeric AS profit
                    UNION ALL
                    SELECT
                        DATE '2026-02-01', 900, 320, 140
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.annual_summary_platform_share_module AS
                    SELECT
                        DATE '2026-01-01' AS period_month,
                        'shopee'::varchar AS platform_code,
                        800::numeric AS gmv
                    UNION ALL
                    SELECT
                        DATE '2026-02-01', 'shopee', 900
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE VIEW api.annual_summary_by_shop_module AS
                    SELECT
                        DATE '2026-01-01' AS period_month,
                        'shopee'::varchar AS platform_code,
                        'shop-a'::varchar AS shop_id,
                        800::numeric AS gmv,
                        10::numeric AS order_count,
                        200::numeric AS visitor_count,
                        300::numeric AS total_cost,
                        120::numeric AS profit,
                        15::numeric AS gross_margin,
                        -22.5::numeric AS net_margin,
                        -0.6::numeric AS roi
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS a_class.sales_targets_a (
                        "年月" varchar(7),
                        "目标销售额" numeric,
                        "目标单量" numeric
                    )
                    """
                )
            )
            await session.execute(text('DELETE FROM a_class.sales_targets_a'))
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets_a ("年月", "目标销售额", "目标单量")
                    VALUES ('2026-01', 1000, 80)
                    """
                )
            )
            await session.commit()

        import backend.main as main_module

        monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )

        async def override_get_async_db():
            async with session_factory() as session:
                yield session

        reloaded = importlib.reload(main_module)
        reloaded.app.dependency_overrides[get_async_db] = override_get_async_db

        async with AsyncClient(
            transport=ASGITransport(app=reloaded.app),
            base_url="http://localhost",
        ) as client:
            kpi_response = await client.get("/api/dashboard/business-overview/kpi", params={"month": "2026-03-01"})
            comparison_response = await client.get(
                "/api/dashboard/business-overview/comparison",
                params={"granularity": "monthly", "date": "2026-03-01"},
            )
            shop_racing_response = await client.get(
                "/api/dashboard/business-overview/shop-racing",
                params={"granularity": "monthly", "date": "2026-03-01", "group_by": "shop"},
            )
            operational_response = await client.get(
                "/api/dashboard/business-overview/operational-metrics",
                params={"month": "2026-03-01"},
            )
            target_response = await client.get(
                "/api/dashboard/annual-summary/target-completion",
                params={"granularity": "yearly", "period": "2026"},
            )
            trend_response = await client.get(
                "/api/dashboard/annual-summary/trend",
                params={"granularity": "yearly", "period": "2026"},
            )
            platform_share_response = await client.get(
                "/api/dashboard/annual-summary/platform-share",
                params={"granularity": "yearly", "period": "2026"},
            )
            by_shop_response = await client.get(
                "/api/dashboard/annual-summary/by-shop",
                params={"granularity": "yearly", "period": "2026"},
            )

        kpi_body = json.loads(kpi_response.content.decode("utf-8"))
        comparison_body = json.loads(comparison_response.content.decode("utf-8"))
        shop_racing_body = json.loads(shop_racing_response.content.decode("utf-8"))
        operational_body = json.loads(operational_response.content.decode("utf-8"))
        target_body = json.loads(target_response.content.decode("utf-8"))
        trend_body = json.loads(trend_response.content.decode("utf-8"))
        platform_share_body = json.loads(platform_share_response.content.decode("utf-8"))
        by_shop_body = json.loads(by_shop_response.content.decode("utf-8"))

        assert kpi_response.status_code == 200
        assert kpi_body["data"]["gmv"] == 321
        assert comparison_response.status_code == 200
        assert comparison_body["data"]["metrics"]["sales_amount"]["today"] == 321
        assert shop_racing_response.status_code == 200
        assert shop_racing_body["data"][0]["gmv"] == 321
        assert operational_response.status_code == 200
        assert operational_body["data"]["operating_result_text"] == "亏损"
        assert target_response.status_code == 200
        assert target_body["data"]["achievement_rate_gmv"] == 80.0
        assert trend_response.status_code == 200
        assert len(trend_body["data"]) == 2
        assert platform_share_response.status_code == 200
        assert platform_share_body["data"][0]["platform_code"] == "shopee"
        assert by_shop_response.status_code == 200
        assert by_shop_body["data"][0]["shop_id"] == "shop-a"

        reloaded.app.dependency_overrides.clear()
        monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
        importlib.reload(main_module)
        await engine.dispose()
