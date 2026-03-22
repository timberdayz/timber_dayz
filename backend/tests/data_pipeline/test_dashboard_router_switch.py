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
    assert "Dashboard router source: Metabase compatibility" in text


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
            target_response = await client.get(
                "/api/dashboard/annual-summary/target-completion",
                params={"granularity": "yearly", "period": "2026"},
            )

        kpi_body = json.loads(kpi_response.content.decode("utf-8"))
        target_body = json.loads(target_response.content.decode("utf-8"))

        assert kpi_response.status_code == 200
        assert kpi_body["data"]["gmv"] == 321
        assert target_response.status_code == 200
        assert target_body["data"]["achievement_rate_gmv"] == 80.0

        reloaded.app.dependency_overrides.clear()
        monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
        importlib.reload(main_module)
        await engine.dispose()
