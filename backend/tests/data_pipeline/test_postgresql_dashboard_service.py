import pytest

from backend.services.postgresql_dashboard_service import (
    PostgresqlDashboardService,
    get_postgresql_dashboard_service,
    rank_inventory_backlog_rows,
    reduce_annual_summary_kpi_rows,
    reduce_business_overview_comparison_rows,
    reduce_business_overview_kpi_rows,
    rank_shop_racing_rows,
    rank_traffic_rows,
)


def test_reduce_business_overview_kpi_rows_single_platform():
    result = reduce_business_overview_kpi_rows(
        [
            {
                "period_month": "2026-03-01",
                "platform_code": "shopee",
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "total_items": 12,
                "profit": 30,
            }
        ]
    )

    assert result["gmv"] == 100
    assert result["order_count"] == 10
    assert result["visitor_count"] == 200
    assert result["conversion_rate"] == 5
    assert result["avg_order_value"] == 10
    assert result["attach_rate"] == 1.2


def test_reduce_business_overview_kpi_rows_multi_platform():
    result = reduce_business_overview_kpi_rows(
        [
            {
                "period_month": "2026-03-01",
                "platform_code": "shopee",
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "total_items": 12,
                "profit": 30,
            },
            {
                "period_month": "2026-03-01",
                "platform_code": "tiktok",
                "gmv": 60,
                "order_count": 6,
                "visitor_count": 100,
                "conversion_rate": 6,
                "avg_order_value": 10,
                "attach_rate": 1.5,
                "total_items": 9,
                "profit": 18,
            },
        ]
    )

    assert result["gmv"] == 160
    assert result["order_count"] == 16
    assert result["visitor_count"] == 300
    assert result["conversion_rate"] == 5.33
    assert result["avg_order_value"] == 10.0
    assert result["attach_rate"] == 1.31

def test_get_postgresql_dashboard_service_returns_singleton():
    service_a = get_postgresql_dashboard_service()
    service_b = get_postgresql_dashboard_service()

    assert isinstance(service_a, PostgresqlDashboardService)
    assert service_a is service_b


def test_reduce_business_overview_comparison_rows_monthly():
    result = reduce_business_overview_comparison_rows(
        current_row={
            "sales_amount": 300,
            "sales_quantity": 30,
            "traffic": 600,
            "conversion_rate": 5,
            "avg_order_value": 10,
            "attach_rate": 1.2,
            "profit": 90,
            "target_sales_amount": 360,
            "target_sales_quantity": 36,
        },
        previous_row={
            "sales_amount": 240,
            "sales_quantity": 24,
            "traffic": 480,
            "conversion_rate": 5,
            "avg_order_value": 10,
            "attach_rate": 1.1,
            "profit": 72,
            "target_sales_amount": 0,
            "target_sales_quantity": 0,
        },
        average_row={
            "sales_amount": 10,
            "sales_quantity": 1,
            "traffic": 20,
            "conversion_rate": 5,
            "avg_order_value": 10,
            "attach_rate": 1.15,
            "profit": 3,
        },
    )

    assert result["metrics"]["sales_amount"]["today"] == 300
    assert result["metrics"]["sales_amount"]["yesterday"] == 240
    assert result["metrics"]["sales_amount"]["average"] == 10
    assert result["metrics"]["sales_amount"]["change"] == 25.0
    assert result["target"]["sales_amount"] == 360
    assert result["target"]["achievement_rate"] == 83.33


def test_rank_inventory_backlog_rows_filters_and_ranks():
    result = rank_inventory_backlog_rows(
        [
            {"platform_code": "shopee", "inventory_value": 50, "estimated_turnover_days": 20},
            {"platform_code": "tiktok", "inventory_value": 80, "estimated_turnover_days": 45},
            {"platform_code": "shopee", "inventory_value": 60, "estimated_turnover_days": 60},
        ],
        min_days=30,
    )

    assert len(result) == 2
    assert result[0]["inventory_value"] == 80
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2


def test_reduce_annual_summary_kpi_rows_yearly():
    result = reduce_annual_summary_kpi_rows(
        [
            {"gmv": 100, "total_cost": 40, "profit": 20},
            {"gmv": 200, "total_cost": 60, "profit": 50},
        ]
    )

    assert result["gmv"] == 300
    assert result["total_cost"] == 100
    assert result["profit"] == 70
    assert result["gross_margin"] == 23.33
    assert result["net_margin"] == -10.0
    assert result["roi"] == -0.3


def test_reduce_annual_summary_target_completion():
    target_gmv = 1000
    target_orders = 80
    achieved = {"gmv": 800, "profit": 120}

    achievement_rate_gmv = round(achieved["gmv"] / target_gmv * 100, 2)

    assert target_gmv == 1000
    assert target_orders == 80
    assert achieved["gmv"] == 800
    assert achievement_rate_gmv == 80.0


def test_rank_shop_racing_rows_desc_by_gmv():
    result = rank_shop_racing_rows(
        [
            {"name": "shop-b", "gmv": 50},
            {"name": "shop-a", "gmv": 100},
        ]
    )

    assert result[0]["name"] == "shop-a"
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_preserves_target_fields(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "shop-a",
                "gmv": 100,
                "order_count": 10,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "profit": 30,
                "target_amount": 120,
                "achievement_rate": 83.33,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-03-01",
        group_by="shop",
    )

    assert result[0]["target_amount"] == 120
    assert result[0]["achievement_rate"] == 83.33


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_monthly_aggregates_shop_time_targets_without_duplicates(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS mart"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS api"))

            await session.execute(
                text(
                    """
                    CREATE TABLE mart.shop_day_kpi (
                        period_date DATE,
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        gmv NUMERIC,
                        order_count NUMERIC,
                        avg_order_value NUMERIC,
                        attach_rate NUMERIC,
                        profit NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE mart.shop_week_kpi (
                        period_week DATE,
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        gmv NUMERIC,
                        order_count NUMERIC,
                        avg_order_value NUMERIC,
                        attach_rate NUMERIC,
                        profit NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE mart.shop_month_kpi (
                        period_month DATE,
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        gmv NUMERIC,
                        order_count NUMERIC,
                        visitor_count NUMERIC,
                        page_views NUMERIC,
                        conversion_rate NUMERIC,
                        avg_order_value NUMERIC,
                        attach_rate NUMERIC,
                        total_items NUMERIC,
                        profit NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.sales_targets (
                        id INTEGER PRIMARY KEY,
                        target_name VARCHAR(255),
                        target_type VARCHAR(64),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER,
                        achieved_amount NUMERIC,
                        achieved_quantity INTEGER,
                        achievement_rate NUMERIC,
                        status VARCHAR(32)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.target_breakdown (
                        target_id INTEGER,
                        breakdown_type VARCHAR(64),
                        platform_code VARCHAR(64),
                        shop_id VARCHAR(255),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER,
                        achievement_rate NUMERIC
                    )
                    """
                )
            )

            await session.execute(
                text(
                    """
                    INSERT INTO mart.shop_month_kpi (
                        period_month, platform_code, shop_id, gmv, order_count,
                        visitor_count, page_views, conversion_rate, avg_order_value,
                        attach_rate, total_items, profit
                    ) VALUES (
                        DATE '2025-09-01', 'shopee', 'shop-3c', 100, 10,
                        0, 0, 0, 10, 1.2, 12, 30
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets (
                        id, target_name, target_type, period_start, period_end,
                        target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, status
                    ) VALUES (
                        1, '2025-09 target', 'shop', DATE '2025-09-01', DATE '2025-09-30',
                        300, 30, 0, 0, 0, 'active'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.target_breakdown (
                        target_id, breakdown_type, platform_code, shop_id, period_start, period_end,
                        target_amount, target_quantity, achievement_rate
                    ) VALUES
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-01', DATE '2025-09-01', 100, 10, 0),
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-02', DATE '2025-09-02', 100, 10, 0),
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-03', DATE '2025-09-03', 100, 10, 0)
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            await execute_sql_target(session, "api.business_overview_shop_racing_module")
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()
        result = await service.get_business_overview_shop_racing(
            granularity="monthly",
            target_date="2025-09-01",
            group_by="shop",
        )

        assert len(result) == 1
        assert result[0]["shop_id"] == "shop-3c"
        assert result[0]["gmv"] == 100
        assert result[0]["target_amount"] == 300
        assert result[0]["achievement_rate"] == 33.33

        await engine.dispose()


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_preserves_today_and_time_gap(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": 1000,
                "monthly_total_achieved": 800,
                "today_sales": 120,
                "monthly_achievement_rate": 80,
                "time_gap": -5,
                "estimated_gross_profit": 200,
                "estimated_expenses": 300,
                "operating_result": -100,
                "monthly_order_count": 10,
                "today_order_count": 2,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    result = await service.get_business_overview_operational_metrics(
        month="2026-03-01",
        platform=None,
    )

    assert result["today_sales"] == 120
    assert result["today_order_count"] == 2
    assert result["time_gap"] == -5


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_comparison_loads_total_month_target_when_rows_have_none(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.sales_targets (
                        id INTEGER PRIMARY KEY,
                        target_name VARCHAR(255),
                        target_type VARCHAR(64),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER,
                        achieved_amount NUMERIC,
                        achieved_quantity INTEGER,
                        achievement_rate NUMERIC,
                        status VARCHAR(32)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets (
                        id, target_name, target_type, period_start, period_end,
                        target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, status
                    ) VALUES (
                        1, '2025年9月常规月度目标', 'shop', DATE '2025-09-01', DATE '2025-09-30',
                        1100000, 10100, 0, 0, 0, 'active'
                    )
                    """
                )
            )
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()

        async def fake_fetch_rows(query, params):
            if "business_overview_comparison_module" in query:
                period_key = params.get("period_key")
                if str(period_key) == "2025-09-01":
                    return [
                        {
                            "sales_amount": 5000,
                            "sales_quantity": 50,
                            "traffic": 1000,
                            "conversion_rate": 5,
                            "avg_order_value": 100,
                            "attach_rate": 1.2,
                            "profit": 300,
                            "target_sales_amount": None,
                            "target_sales_quantity": None,
                        }
                    ]
                return []
            return []

        monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
        result = await service.get_business_overview_comparison(
            granularity="monthly",
            target_date="2025-09-01",
            platform=None,
        )

        assert result["target"]["sales_amount"] == 1100000
        assert result["target"]["sales_quantity"] == 10100

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_loads_total_targets_and_costs(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.sales_targets (
                        id INTEGER PRIMARY KEY,
                        target_name VARCHAR(255),
                        target_type VARCHAR(64),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER,
                        achieved_amount NUMERIC,
                        achieved_quantity INTEGER,
                        achievement_rate NUMERIC,
                        status VARCHAR(32)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.operating_costs (
                        "店铺ID" VARCHAR(255),
                        "年月" VARCHAR(7),
                        "租金" NUMERIC,
                        "工资" NUMERIC,
                        "水电费" NUMERIC,
                        "其他成本" NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets (
                        id, target_name, target_type, period_start, period_end,
                        target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, status
                    ) VALUES (
                        1, '2025年9月常规月度目标', 'shop', DATE '2025-09-01', DATE '2025-09-30',
                        1100000, 10100, 0, 0, 0, 'active'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.operating_costs ("店铺ID", "年月", "租金", "工资", "水电费", "其他成本")
                    VALUES
                        ('shopee新加坡3C店', '2025-09', 100, 200, 300, 400),
                        ('Tiktok 2店', '2025-09', 100, 200, 200, 300)
                    """
                )
            )
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()

        async def fake_fetch_rows(query, params):
            return [
                {
                    "monthly_target": 0,
                    "monthly_total_achieved": 25000,
                    "today_sales": 1200,
                    "monthly_achievement_rate": 0,
                    "time_gap": 0,
                    "estimated_gross_profit": 3000,
                    "estimated_expenses": 0,
                    "operating_result": 0,
                    "monthly_order_count": 200,
                    "today_order_count": 12,
                }
            ]

        monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
        result = await service.get_business_overview_operational_metrics(
            month="2025-09-01",
            platform=None,
        )

        assert result["monthly_target"] == 1100000
        assert result["estimated_expenses"] == 1800
        assert result["monthly_total_achieved"] == 25000

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_load_target_summary_daily_without_platform_avoids_null_platform_sql_error(monkeypatch):
    from datetime import date
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.sales_targets (
                        id INTEGER PRIMARY KEY,
                        target_name VARCHAR(255),
                        target_type VARCHAR(64),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER,
                        achieved_amount NUMERIC,
                        achieved_quantity INTEGER,
                        achievement_rate NUMERIC,
                        status VARCHAR(32)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.target_breakdown (
                        target_id INTEGER,
                        breakdown_type VARCHAR(64),
                        platform_code VARCHAR(64),
                        shop_id VARCHAR(255),
                        period_start DATE,
                        period_end DATE,
                        target_amount NUMERIC,
                        target_quantity INTEGER
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets (
                        id, target_name, target_type, period_start, period_end,
                        target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, status
                    ) VALUES (
                        1, '2026年3月目标', 'shop', DATE '2026-03-01', DATE '2026-03-31',
                        1000, 80, 0, 0, 0, 'active'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.target_breakdown (
                        target_id, breakdown_type, platform_code, shop_id, period_start, period_end, target_amount, target_quantity
                    ) VALUES (
                        1, 'time', 'shopee', NULL, DATE '2026-03-24', DATE '2026-03-24', 30, 2
                    )
                    """
                )
            )
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()
        result = await service._load_target_summary(
            granularity="daily",
            period_start=date(2026, 3, 24),
            period_end=date(2026, 3, 24),
            platform=None,
        )

        assert result["target_amount"] == 30
        assert result["target_quantity"] == 2

        await engine.dispose()


def test_rank_traffic_rows_by_visitors():
    result = rank_traffic_rows(
        [
            {"name": "shop-b", "visitor_count": 50, "page_views": 80},
            {"name": "shop-a", "visitor_count": 100, "page_views": 120},
        ],
        dimension="visitor",
    )

    assert result[0]["name"] == "shop-a"
    assert result[0]["rank"] == 1


def test_rank_traffic_rows_by_page_views():
    result = rank_traffic_rows(
        [
            {"name": "shop-b", "visitor_count": 50, "page_views": 180},
            {"name": "shop-a", "visitor_count": 100, "page_views": 120},
        ],
        dimension="pv",
    )

    assert result[0]["name"] == "shop-b"
    assert result[0]["rank"] == 1


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_reads_real_kpi_chain(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS semantic.fact_orders_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        paid_amount NUMERIC,
                        order_id VARCHAR(128),
                        product_quantity NUMERIC,
                        profit NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS semantic.fact_analytics_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        visitor_count NUMERIC,
                        page_views NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_orders_atomic (
                        platform_code, shop_id, granularity, metric_date,
                        paid_amount, order_id, product_quantity, profit
                    )
                    VALUES (
                        'shopee', 'shop-a', 'daily', DATE '2026-03-01',
                        100, 'o-1', 12, 30
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_analytics_atomic (
                        platform_code, shop_id, granularity, metric_date, visitor_count, page_views
                    )
                    VALUES (
                        'shopee', 'shop-a', 'daily', DATE '2026-03-01', 200, 300
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            for target in (
                "mart.shop_day_kpi",
                "mart.shop_week_kpi",
                "mart.shop_month_kpi",
                "mart.platform_month_kpi",
                "api.business_overview_kpi_module",
            ):
                await execute_sql_target(session, target)
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()
        result = await service.get_business_overview_kpi("2026-03-01", None)

        assert result["gmv"] == 100
        assert result["order_count"] == 1
        assert result["visitor_count"] == 200
        assert result["avg_order_value"] == 100
        assert result["attach_rate"] == 12

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_reads_real_inventory_chain(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse

    from backend.services.data_pipeline.refresh_runner import execute_sql_target

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)
        engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS semantic.fact_products_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        product_id VARCHAR(128),
                        product_name VARCHAR(256),
                        platform_sku VARCHAR(128),
                        sales_amount NUMERIC,
                        order_count NUMERIC,
                        sales_volume NUMERIC,
                        page_views NUMERIC,
                        unique_visitors NUMERIC,
                        impressions NUMERIC,
                        clicks NUMERIC,
                        conversion_rate NUMERIC,
                        review_count NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS semantic.fact_inventory_snapshot (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        product_id VARCHAR(128),
                        product_name VARCHAR(256),
                        platform_sku VARCHAR(128),
                        sku_id VARCHAR(128),
                        product_sku VARCHAR(128),
                        warehouse_name VARCHAR(128),
                        warehouse_code VARCHAR(64),
                        available_stock NUMERIC,
                        on_hand_stock NUMERIC,
                        reserved_stock NUMERIC,
                        in_transit_stock NUMERIC,
                        stockout_qty NUMERIC,
                        reorder_point NUMERIC,
                        safety_stock NUMERIC,
                        unit_cost NUMERIC,
                        inventory_value NUMERIC,
                        ingest_timestamp TIMESTAMP,
                        currency_code VARCHAR(3),
                        data_hash VARCHAR(64)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS semantic.fact_orders_atomic (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        granularity VARCHAR(32),
                        metric_date DATE,
                        platform_sku VARCHAR(128),
                        product_sku VARCHAR(128),
                        product_quantity NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_products_atomic (
                        platform_code, shop_id, granularity, metric_date, product_id,
                        product_name, platform_sku, sales_amount, order_count, sales_volume,
                        page_views, unique_visitors, impressions, clicks, conversion_rate, review_count
                    )
                    VALUES (
                        'shopee', 'shop-a', 'daily', DATE '2026-03-01', 'p-1',
                        'demo product', 'sku-a', 100, 10, 12,
                        300, 200, 500, 60, 0.05, 8
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_inventory_snapshot (
                        platform_code, shop_id, granularity, metric_date, product_id, product_name,
                        platform_sku, sku_id, product_sku, warehouse_name, warehouse_code,
                        available_stock, on_hand_stock, reserved_stock, in_transit_stock, stockout_qty,
                        reorder_point, safety_stock, unit_cost, inventory_value, ingest_timestamp,
                        currency_code, data_hash
                    )
                    VALUES (
                        'shopee', 'shop-a', 'snapshot', DATE '2026-03-01', 'p-1', 'demo product',
                        'sku-a', 'sku-id-a', 'psku-a', 'main warehouse', 'WH1',
                        450, 450, 0, 0, 0,
                        10, 20, 5, 2250, TIMESTAMP '2026-03-01 00:00:00',
                        'CNY', 'hash-inv-1'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO semantic.fact_orders_atomic (
                        platform_code, shop_id, granularity, metric_date, platform_sku, product_sku, product_quantity
                    )
                    VALUES (
                        'shopee', 'shop-a', 'daily', DATE '2026-03-01', 'sku-a', 'psku-a', 9
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            for target in (
                "mart.product_day_kpi",
                "mart.inventory_current",
                "mart.inventory_backlog_base",
                "api.business_overview_inventory_backlog_module",
                "api.clearance_ranking_module",
            ):
                await execute_sql_target(session, target)
            await session.commit()

        monkeypatch.setattr(
            "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
            session_factory,
        )
        service = PostgresqlDashboardService()
        backlog = await service.get_business_overview_inventory_backlog(min_days=30)
        clearance = await service.get_clearance_ranking(min_days=30, limit=10)

        assert len(backlog) == 1
        assert backlog[0]["platform_code"] == "shopee"
        assert backlog[0]["rank"] == 1
        assert len(clearance) == 1
        assert clearance[0]["platform_code"] == "shopee"
        assert clearance[0]["estimated_turnover_days"] >= 30

        await engine.dispose()
