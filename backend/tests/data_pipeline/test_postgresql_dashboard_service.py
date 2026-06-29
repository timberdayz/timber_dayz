from datetime import date

import pytest
from sqlalchemy.exc import ProgrammingError
from unittest.mock import AsyncMock

import backend.services.postgresql_dashboard_service as dashboard_service_module
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


def test_reduce_business_overview_kpi_rows_calculates_pv_uv_funnel_metrics():
    result = reduce_business_overview_kpi_rows(
        [
            {
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "page_views": 500,
                "impressions": 1000,
                "total_items": 12,
                "profit": 30,
            },
            {
                "gmv": 60,
                "order_count": 6,
                "visitor_count": 100,
                "page_views": 300,
                "impressions": 500,
                "total_items": 9,
                "profit": 18,
            },
        ]
    )

    assert result["visitor_count"] == 300
    assert result["page_views"] == 800
    assert result["impressions"] == 1500
    assert result["uv_conversion_rate"] == 5.33
    assert result["pv_conversion_rate"] == 2.0
    assert result["conversion_rate"] == 5.33
    assert result["visit_rate"] == 20.0
    assert result["browse_depth"] == 2.67
    assert result["exposure_order_rate"] == 1.07


def test_reduce_business_overview_kpi_rows_preserves_missing_pv_uv_funnel_inputs():
    result = reduce_business_overview_kpi_rows(
        [
            {
                "gmv": 100,
                "order_count": 10,
                "visitor_count": None,
                "page_views": None,
                "impressions": None,
                "total_items": 12,
                "profit": 30,
            }
        ]
    )

    assert result["visitor_count"] is None
    assert result["page_views"] is None
    assert result["impressions"] is None
    assert result["uv_conversion_rate"] is None
    assert result["pv_conversion_rate"] is None
    assert result["conversion_rate"] is None
    assert result["visit_rate"] is None
    assert result["browse_depth"] is None
    assert result["exposure_order_rate"] is None


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_kpi_reads_from_platform_month_kpi(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_month": "2026-04-01",
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

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    async def fake_load_active_employee_count(_period_key):
        return 0

    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)
    result = await service.get_business_overview_kpi(month="2026-04-01", platform=None)

    assert result["gmv"] == 100
    assert len(captured) == 2
    query, params = captured[0]
    assert "FROM api.business_overview_kpi_module" in query
    assert str(params["period_key"]) == "2026-04-01"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_monthly_kpi_supports_platform_filter(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_key": "2026-04-01",
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

    async def fake_load_active_employee_count(_period_key):
        return 0

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)

    result = await service.get_business_overview_kpi(month="2026-04-01", platform="shopee")

    assert result["gmv"] == 100
    assert len(captured) == 2
    query, params = captured[0]
    assert "FROM api.business_overview_kpi_module" in query
    assert "platform_code = :platform_code" in query
    assert str(params["period_key"]) == "2026-04-01"
    assert params["platform_code"] == "shopee"


@pytest.mark.asyncio
async def test_business_overview_data_freshness_flags_orders_lagging_traffic(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        if "information_schema.tables" in query:
            return [
                {"table_name": "fact_shopee_orders_monthly"},
                {"table_name": "fact_shopee_analytics_monthly"},
            ]
        if "fact_shopee_orders_monthly" in query:
            return [
                {
                    "row_count": 100,
                    "period_start_date": date(2026, 6, 1),
                    "period_end_date": date(2026, 6, 10),
                    "latest_metric_date": date(2026, 6, 1),
                    "latest_ingest_timestamp": "2026-06-11T13:35:41",
                }
            ]
        if "fact_shopee_analytics_monthly" in query:
            return [
                {
                    "row_count": 100,
                    "period_start_date": date(2026, 6, 1),
                    "period_end_date": date(2026, 6, 16),
                    "latest_metric_date": date(2026, 6, 1),
                    "latest_ingest_timestamp": "2026-06-17T10:46:34",
                }
            ]
        return []

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_data_freshness(platform="shopee")

    assert result["is_stale"] is True
    assert result["orders"]["period_end_date"] == date(2026, 6, 10)
    assert result["traffic"]["period_end_date"] == date(2026, 6, 16)
    assert "orders period_end_date 2026-06-10 lags traffic 2026-06-16" in result["warnings"]
    assert result["table_checks"][0]["table_name"] == "fact_shopee_orders_monthly"
    assert result["table_checks"][0]["is_stale"] is True
    assert captured[-1][1]["platform_code"] == "shopee"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_kpi_returns_previous_period_changes(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        if str(params["period_key"]) == "2026-03-01":
            return [
                {
                    "period_key": "2026-03-01",
                    "platform_code": "shopee",
                    "gmv": 100,
                    "order_count": 5,
                    "visitor_count": 100,
                    "page_views": 200,
                    "impressions": 500,
                    "total_items": 5,
                    "profit": 20,
                }
            ]
        return [
            {
                "period_key": "2026-04-01",
                "platform_code": "shopee",
                "gmv": 200,
                "order_count": 10,
                "visitor_count": 150,
                "page_views": 300,
                "impressions": 750,
                "total_items": 15,
                "profit": 60,
            }
        ]

    async def fake_load_active_employee_count(_period_key):
        return 2

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)

    result = await service.get_business_overview_kpi(month="2026-04-01", platform="shopee")

    assert len(captured) == 2
    assert result["gmv"] == 200
    assert result["gmv_change"] == 100.0
    assert result["order_count_change"] == 100.0
    assert result["visitor_count_change"] == 50.0
    assert result["labor_efficiency_change"] == 100.0


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_kpi_shop_filter_reads_shop_mart(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_key": params["period_key"],
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "gmv": 100,
                "order_count": 10,
                "visitor_count": 200,
                "page_views": 400,
                "impressions": 1000,
                "total_items": 12,
                "profit": 30,
            }
        ]

    async def fake_load_active_employee_count(_period_key):
        return 0

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)

    result = await service.get_business_overview_kpi(
        month="2026-04-01",
        platform=None,
        shop_id="shop-1",
    )

    assert result["gmv"] == 100
    query, params = captured[0]
    assert "FROM mart.shop_month_kpi" in query
    assert "shop_id = :shop_id" in query
    assert params["shop_id"] == "shop-1"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_kpi_supports_granularity_specific_platform_sources(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_key": "2026-04-07",
                "platform_code": "shopee",
                "gmv": 120,
                "order_count": 12,
                "visitor_count": 300,
                "conversion_rate": 4,
                "avg_order_value": 10,
                "attach_rate": 1.5,
                "total_items": 18,
                "profit": 36,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    async def fake_load_active_employee_count(_period_key):
        return 0

    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)

    result = await service.get_business_overview_kpi(
        granularity="daily",
        target_date="2026-04-07",
        platform="shopee",
    )

    assert result["gmv"] == 120
    assert len(captured) == 2
    query, params = captured[0]
    assert "FROM mart.platform_day_kpi" in query
    assert str(params["period_key"]) == "2026-04-07"
    assert params["platform_code"] == "shopee"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_kpi_computes_labor_efficiency_from_employee_count(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "period_month": "2026-04-01",
                "platform_code": "shopee",
                "gmv": 10000,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 1000,
                "attach_rate": 1.2,
                "total_items": 12,
                "profit": 3000,
            }
        ]

    async def fake_load_active_employee_count(_period_key):
        return 2

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(
        service,
        "_load_active_employee_count",
        fake_load_active_employee_count,
        raising=False,
    )

    result = await service.get_business_overview_kpi(month="2026-04-01", platform=None)

    assert result["labor_efficiency"] == 5000.0


@pytest.mark.asyncio
async def test_load_active_employee_count_falls_back_when_identity_column_missing(monkeypatch):
    service = PostgresqlDashboardService()

    class _OrigError(Exception):
        pass

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        def __init__(self):
            self.calls = 0
            self.rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                raise ProgrammingError(
                    str(stmt),
                    None,
                    _OrigError('column "employee_identity_type" does not exist'),
                )
            return _Result(7)

        async def rollback(self):
            self.rolled_back = True

    session = _Session()
    monkeypatch.setattr(
        "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
        lambda: session,
    )

    result = await service._load_active_employee_count("2026-04-01")

    assert result == 7
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_load_active_employee_count_returns_zero_when_employee_table_missing(monkeypatch):
    service = PostgresqlDashboardService()

    class _OrigError(Exception):
        pass

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            raise ProgrammingError(
                str(stmt),
                None,
                _OrigError('relation "a_class.employees" does not exist'),
            )

        async def rollback(self):
            return None

    monkeypatch.setattr(
        "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
        lambda: _Session(),
    )

    result = await service._load_active_employee_count("2026-04-01")

    assert result == 0


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_annual_summary_kpi_uses_platform_month_aggregate(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {"gmv": 100, "total_cost": 40, "profit": 20},
            {"gmv": 200, "total_cost": 60, "profit": 50},
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_annual_summary_kpi(granularity="yearly", period="2026")

    assert result["gmv"] == 300
    assert len(captured) == 1
    query, params = captured[0]
    assert "platform_month" in query.lower()
    assert "annual_summary_shop_month" not in query
    assert str(params["period_start"]) == "2026-01-01"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_inventory_backlog_honors_limit(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_summary():
        return {"total_value": 1000}

    async def fake_ranked_rows(*, source_table, min_days, limit, period_start=None, period_end=None):
        assert source_table == "api.business_overview_inventory_backlog_module"
        assert min_days == 30
        return [{"rank": index} for index in range(1, limit + 1)]

    monkeypatch.setattr(service, "_load_inventory_backlog_summary", fake_summary)
    monkeypatch.setattr(service, "_load_ranked_inventory_backlog_module_rows", fake_ranked_rows)

    result = await service.get_business_overview_inventory_backlog(min_days=30, limit=20)

    assert len(result["top_products"]) == 20
    assert result["top_products"][0]["rank"] == 1
    assert result["top_products"][-1]["rank"] == 20


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_inventory_backlog_defaults_to_board_limit(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_summary():
        return {"total_value": 1000}

    async def fake_ranked_rows(*, source_table, min_days, limit, period_start=None, period_end=None):
        assert source_table == "api.business_overview_inventory_backlog_module"
        assert min_days == 30
        assert limit == 20
        return [{"rank": 1}]

    monkeypatch.setattr(service, "_load_inventory_backlog_summary", fake_summary)
    monkeypatch.setattr(service, "_load_ranked_inventory_backlog_module_rows", fake_ranked_rows)

    result = await service.get_business_overview_inventory_backlog(min_days=30)

    assert result["top_products"] == [{"rank": 1}]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_inventory_backlog_filters_by_requested_period(monkeypatch):
    service = PostgresqlDashboardService()
    captured = {}

    async def fake_summary(period_start=None, period_end=None):
        captured["summary_period_start"] = period_start
        captured["summary_period_end"] = period_end
        return {"total_value": 1000}

    async def fake_ranked_rows(*, source_table, min_days, limit, period_start=None, period_end=None):
        captured["rows_period_start"] = period_start
        captured["rows_period_end"] = period_end
        return [{"rank": 1}]

    monkeypatch.setattr(service, "_load_inventory_backlog_summary", fake_summary)
    monkeypatch.setattr(service, "_load_ranked_inventory_backlog_module_rows", fake_ranked_rows)

    result = await service.get_business_overview_inventory_backlog(
        min_days=30,
        limit=20,
        granularity="weekly",
        target_date="2026-04-15",
    )

    assert result["top_products"] == [{"rank": 1}]
    assert str(captured["summary_period_start"]) == "2026-04-13"
    assert str(captured["summary_period_end"]) == "2026-04-19"
    assert str(captured["rows_period_start"]) == "2026-04-13"
    assert str(captured["rows_period_end"]) == "2026-04-19"


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
            {"platform_code": "shopee", "inventory_value": 50, "estimated_turnover_days": 20, "estimated_stagnant_days": 0, "stagnant_snapshot_count": 0},
            {"platform_code": "tiktok", "inventory_value": 80, "estimated_turnover_days": 45, "estimated_stagnant_days": 10, "stagnant_snapshot_count": 1},
            {"platform_code": "shopee", "inventory_value": 60, "estimated_turnover_days": 60, "estimated_stagnant_days": 14, "stagnant_snapshot_count": 2},
        ],
        min_days=30,
    )

    assert len(result) == 2
    assert result[0]["inventory_value"] == 60
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2
    assert "risk_level" in result[0]
    assert "clearance_priority_score" in result[0]


def test_rank_inventory_backlog_rows_uses_risk_and_priority_fields():
    result = rank_inventory_backlog_rows(
        [
            {
                "platform_code": "shopee",
                "inventory_value": 100,
                "estimated_turnover_days": 70,
                "estimated_stagnant_days": 12,
                "stagnant_snapshot_count": 3,
            }
        ],
        min_days=30,
    )

    assert result[0]["risk_level"] == "high"
    assert result[0]["clearance_priority_score"] > 0


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


class _FetchOneResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


@pytest.mark.asyncio
async def test_annual_summary_target_completion_reads_active_parent_targets(monkeypatch):
    service = PostgresqlDashboardService()
    service.get_annual_summary_kpi = AsyncMock(return_value={"gmv": 200000.0, "profit": 50000.0})

    class _Db:
        def __init__(self):
            self.statements = []
            self.params = []

        async def execute(self, statement, params):
            self.statements.append(str(statement))
            self.params.append(params)
            return _FetchOneResult((400000.0, 3000))

    db = _Db()

    result = await service.get_annual_summary_target_completion(db, "monthly", "2026-04")

    assert "a_class.sales_targets" in db.statements[0]
    assert "sales_targets_a" not in db.statements[0]
    assert db.params[0] == {
        "period_start": date(2026, 4, 1),
        "period_end": date(2026, 4, 30),
    }
    assert result["target_gmv"] == 400000.0
    assert result["target_orders"] == 3000
    assert result["achievement_rate_gmv"] == 50.0


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


def test_rank_shop_racing_rows_breaks_gmv_ties_by_profit_then_orders():
    result = rank_shop_racing_rows(
        [
            {"name": "shop-low-profit", "gmv": 100, "profit": 10, "order_count": 20},
            {"name": "shop-more-orders", "gmv": 100, "profit": 30, "order_count": 5},
            {"name": "shop-high-profit", "gmv": 100, "profit": 30, "order_count": 10},
        ]
    )

    assert [row["name"] for row in result] == [
        "shop-high-profit",
        "shop-more-orders",
        "shop-low-profit",
    ]
    assert [row["rank"] for row in result] == [1, 2, 3]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_comparison_reads_from_platform_aggregate_source(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_key": "2026-04-01",
                "sales_amount": 5000,
                "sales_quantity": 50,
                "traffic": 1000,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.2,
                "profit": 300,
            },
            {
                "period_key": "2026-03-01",
                "sales_amount": 4000,
                "sales_quantity": 40,
                "traffic": 800,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.1,
                "profit": 200,
            },
        ]

    async def fake_load_target_summary(granularity, period_start, period_end, platform=None):
        return {"target_amount": 6000, "target_quantity": 60}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)

    result = await service.get_business_overview_comparison(
        granularity="monthly",
        target_date="2026-04-01",
        platform=None,
    )

    assert result["metrics"]["sales_amount"]["today"] == 5000
    assert result["target"]["sales_amount"] == 6000
    assert len(captured) == 1
    assert all("FROM api.business_overview_comparison_platform_module" in query for query, _ in captured)
    assert "period_key >= :range_start" in captured[0][0]
    assert "period_key <= :range_end" in captured[0][0]
    assert str(captured[0][1]["range_start"]) == "2026-03-01"
    assert str(captured[0][1]["range_end"]) == "2026-04-01"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_comparison_reuses_current_rows_for_monthly_average(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "period_key": "2026-04-01",
                "sales_amount": 5000,
                "sales_quantity": 50,
                "traffic": 1000,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.2,
                "profit": 300,
            },
            {
                "period_key": "2026-03-01",
                "sales_amount": 4000,
                "sales_quantity": 40,
                "traffic": 800,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.1,
                "profit": 200,
            },
        ]

    async def fake_load_target_summary(granularity, period_start, period_end, platform=None):
        return {"target_amount": 6000, "target_quantity": 60}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)

    result = await service.get_business_overview_comparison(
        granularity="monthly",
        target_date="2026-04-01",
        platform=None,
    )

    assert result["metrics"]["sales_amount"]["average"] == 5000
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_comparison_uses_total_items_for_sales_quantity_but_order_count_for_rate_and_aov(
    monkeypatch,
):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "period_key": "2026-04-01",
                "sales_amount": 5000,
                "sales_quantity": 80,
                "order_count": 50,
                "total_items": 80,
                "traffic": 1000,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.6,
                "profit": 300,
            },
            {
                "period_key": "2026-03-01",
                "sales_amount": 4000,
                "sales_quantity": 64,
                "order_count": 40,
                "total_items": 64,
                "traffic": 800,
                "conversion_rate": 5,
                "avg_order_value": 100,
                "attach_rate": 1.6,
                "profit": 200,
            },
        ]

    async def fake_load_target_summary(granularity, period_start, period_end, platform=None):
        return {"target_amount": 6000, "target_quantity": 60}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)

    result = await service.get_business_overview_comparison(
        granularity="monthly",
        target_date="2026-04-01",
        platform=None,
    )

    assert result["metrics"]["sales_quantity"]["today"] == 80
    assert result["metrics"]["conversion_rate"]["today"] == 5
    assert result["metrics"]["avg_order_value"]["today"] == 100
    assert result["metrics"]["attach_rate"]["today"] == 1.6


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_preserves_target_fields(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
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
    assert "api.business_overview_shop_racing_monthly_module" in captured[0][0]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_daily_keeps_generic_module(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "granularity": "daily",
                "period_key": "2026-03-02",
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
        granularity="daily",
        target_date="2026-03-02",
        group_by="shop",
    )

    assert result[0]["target_amount"] == 120
    assert "api.business_overview_shop_racing_module" in captured[0][0]
    assert "api.business_overview_shop_racing_monthly_module" not in captured[0][0]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_returns_previous_period_changes(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "granularity": "monthly",
                "period_key": date(2026, 5, 1),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "display_name": "Shop A",
                "gmv": 120,
                "order_count": 12,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "profit": 30,
                "target_amount": 150,
                "achievement_rate": 80,
            },
            {
                "granularity": "monthly",
                "period_key": date(2026, 4, 1),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "display_name": "Shop A",
                "gmv": 100,
                "order_count": 10,
                "avg_order_value": 10,
                "attach_rate": 1.1,
                "profit": 20,
                "target_amount": 125,
                "achievement_rate": 70,
            },
            {
                "granularity": "monthly",
                "period_key": date(2026, 5, 1),
                "platform_code": "tiktok",
                "shop_id": "shop-b",
                "display_name": "Shop B",
                "gmv": 50,
                "order_count": 5,
                "avg_order_value": 10,
                "attach_rate": 1.0,
                "profit": 0,
                "target_amount": 0,
                "achievement_rate": 0,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-05-01",
        group_by="shop",
    )

    shop_a = next(row for row in result if row["shop_id"] == "shop-a")
    assert shop_a["gmv_previous"] == 100
    assert shop_a["profit_previous"] == 20
    assert shop_a["avg_order_value_previous"] == 10
    assert shop_a["profit_margin_previous"] == 20
    assert shop_a["order_count_previous"] == 10
    assert shop_a["achievement_rate_previous"] == 70
    assert shop_a["gmv_change_rate"] == 20
    assert shop_a["profit_change_rate"] == 50
    assert shop_a["avg_order_value_change_rate"] == 0
    assert shop_a["profit_margin_change_value"] == 5
    assert shop_a["order_count_change_rate"] == 20
    assert shop_a["achievement_rate_change_value"] == 10

    shop_b = next(row for row in result if row["shop_id"] == "shop-b")
    assert shop_b["gmv_previous"] is None
    assert shop_b["profit_previous"] is None
    assert shop_b["avg_order_value_previous"] is None
    assert shop_b["profit_margin_previous"] is None
    assert shop_b["order_count_previous"] is None
    assert shop_b["achievement_rate_previous"] is None
    assert shop_b["gmv_change_rate"] is None
    assert shop_b["profit_change_rate"] is None
    assert shop_b["avg_order_value_change_rate"] is None
    assert shop_b["profit_margin_change_value"] is None
    assert shop_b["order_count_change_rate"] is None
    assert shop_b["achievement_rate_change_value"] is None
    assert captured[0][1]["period_key"] == date(2026, 5, 1)
    assert captured[0][1]["previous_period_key"] == date(2026, 4, 1)
    assert "src.period_key IN (:period_key, :previous_period_key)" in captured[0][0]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_account_group_calculates_changes_after_aggregation(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "weekly",
                "period_key": date(2026, 5, 4),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "shop_account_id": "account-1",
                "account_display_name": "Account 1",
                "gmv": 120,
                "order_count": 12,
                "profit": 30,
                "target_amount": 150,
                "achievement_rate": 80,
            },
            {
                "granularity": "weekly",
                "period_key": date(2026, 5, 4),
                "platform_code": "tiktok",
                "shop_id": "shop-b",
                "shop_account_id": "account-1",
                "account_display_name": "Account 1",
                "gmv": 80,
                "order_count": 8,
                "profit": 10,
                "target_amount": 50,
                "achievement_rate": 160,
            },
            {
                "granularity": "weekly",
                "period_key": date(2026, 4, 27),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "shop_account_id": "account-1",
                "account_display_name": "Account 1",
                "gmv": 100,
                "order_count": 10,
                "profit": 20,
                "target_amount": 125,
                "achievement_rate": 80,
            },
            {
                "granularity": "weekly",
                "period_key": date(2026, 4, 27),
                "platform_code": "tiktok",
                "shop_id": "shop-b",
                "shop_account_id": "account-1",
                "account_display_name": "Account 1",
                "gmv": 50,
                "order_count": 5,
                "profit": 10,
                "target_amount": 50,
                "achievement_rate": 100,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="weekly",
        target_date="2026-05-07",
        group_by="account",
    )

    assert len(result) == 1
    assert result[0]["gmv"] == 200
    assert result[0]["gmv_previous"] == 150
    assert result[0]["profit_previous"] == 30
    assert result[0]["avg_order_value_previous"] == 10
    assert result[0]["profit_margin_previous"] == 20
    assert result[0]["order_count_previous"] == 15
    assert result[0]["achievement_rate_previous"] == 85.71
    assert result[0]["gmv_change_rate"] == 33.33
    assert result[0]["profit_change_rate"] == 33.33
    assert result[0]["avg_order_value_change_rate"] == 0
    assert result[0]["profit_margin_change_value"] == 0
    assert result[0]["order_count_change_rate"] == 33.33
    assert result[0]["achievement_rate"] == 100
    assert result[0]["achievement_rate_change_value"] == 14.29


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_rate_fields_handle_zero_or_missing_previous(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": date(2026, 5, 1),
                "platform_code": "shopee",
                "shop_id": "shop-a",
                "display_name": "Shop A",
                "gmv": 100,
                "order_count": 2,
                "avg_order_value": 50,
                "profit": 10,
                "target_amount": 100,
                "achievement_rate": 100,
            },
            {
                "granularity": "monthly",
                "period_key": date(2026, 4, 1),
                "platform_code": "shopee",
                "shop_id": "shop-a",
                "display_name": "Shop A",
                "gmv": 0,
                "order_count": 0,
                "avg_order_value": 0,
                "profit": 0,
                "target_amount": 100,
                "achievement_rate": 0,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-05-01",
        group_by="shop",
    )

    row = result[0]
    assert row["avg_order_value_previous"] == 0
    assert row["avg_order_value_change_rate"] is None
    assert row["profit_margin_previous"] is None
    assert row["profit_margin_change_value"] is None


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_prefers_resolved_display_name(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200830",
                "display_name": "Singapore(HX Home)",
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

    assert result[0]["name"] == "Singapore(HX Home)"
    assert result[0]["shop_id"] == "1308200830"
    assert "api.business_overview_shop_racing_monthly_module" in captured[0][0]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_masks_unknown_name(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "unknown",
                "display_name": None,
                "gmv": 100,
                "order_count": 10,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "profit": 30,
                "target_amount": 0,
                "achievement_rate": 0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-03-01",
        group_by="shop",
    )

    assert result[0]["name"] == "未匹配店铺"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_account_group_uses_shop_account_hierarchy(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200830",
                "display_name": "Singapore(HX Home)",
                "shop_account_id": "shopee_sg_hx_home",
                "account_display_name": "Main SG / HX Home",
                "main_account_id": "main_shopee_sg",
                "main_account_name": "Main SG",
                "gmv": 100,
                "order_count": 10,
                "avg_order_value": 10,
                "attach_rate": 1.2,
                "profit": 30,
                "target_amount": 120,
                "achievement_rate": 83.33,
            },
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200831",
                "display_name": "Singapore(HX Annex)",
                "shop_account_id": "shopee_sg_hx_home",
                "account_display_name": "Main SG / HX Home",
                "main_account_id": "main_shopee_sg",
                "main_account_name": "Main SG",
                "gmv": 60,
                "order_count": 6,
                "avg_order_value": 10,
                "attach_rate": 1.1,
                "profit": 18,
                "target_amount": 80,
                "achievement_rate": 75,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-03-01",
        group_by="account",
    )

    assert len(result) == 1
    assert result[0]["name"] == "Main SG / HX Home"
    assert result[0]["shop_account_id"] == "shopee_sg_hx_home"
    assert result[0]["main_account_id"] == "main_shopee_sg"
    assert result[0]["gmv"] == 160
    assert result[0]["profit"] == 48
    assert result[0]["target_amount"] == 200


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_shop_racing_platform_group_sums_profit(monkeypatch):
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
                "profit": 30,
                "target_amount": 120,
            },
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "shop-b",
                "gmv": 60,
                "order_count": 6,
                "profit": 18,
                "target_amount": 80,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-03-01",
        group_by="platform",
    )

    assert len(result) == 1
    assert result[0]["name"] == "shopee"
    assert result[0]["gmv"] == 160
    assert result[0]["profit"] == 48
    assert result[0]["target_amount"] == 200


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
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE core.dim_shops (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        shop_name VARCHAR(256)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE core.main_accounts (
                        id SERIAL PRIMARY KEY,
                        main_account_id VARCHAR(100),
                        main_account_name VARCHAR(200)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        platform VARCHAR(50),
                        main_account_id VARCHAR(100),
                        store_name VARCHAR(200),
                        platform_shop_id VARCHAR(256),
                        shop_account_id VARCHAR(100)
                    )
                    """
                )
            )

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
                    CREATE TABLE semantic.fact_orders_monthly_atomic (
                        metric_date DATE,
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        order_id VARCHAR(128),
                        paid_amount NUMERIC,
                        product_quantity NUMERIC,
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
                    INSERT INTO semantic.fact_orders_monthly_atomic (
                        metric_date, platform_code, shop_id, order_id, paid_amount, product_quantity, profit
                    ) VALUES (
                        DATE '2025-09-01', 'shopee', 'shop-3c', 'o-1', 100, 12, 30
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
                    ) VALUES
                        (
                            1, '2025-09 target', 'shop', DATE '2025-09-01', DATE '2025-09-30',
                            300, 30, 0, 0, 0, 'active'
                        ),
                        (
                            2, '2025-08 target', 'shop', DATE '2025-08-01', DATE '2025-08-31',
                            999, 99, 0, 0, 0, 'active'
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
                        (2, 'shop', 'shopee', 'shop-3c', DATE '2025-08-01', DATE '2025-08-31', 999, 99, 0),
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-01', DATE '2025-09-01', 100, 10, 0),
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-02', DATE '2025-09-02', 100, 10, 0),
                        (1, 'shop_time', 'shopee', 'shop-3c', DATE '2025-09-03', DATE '2025-09-03', 100, 10, 0)
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            for target in (
                "api.business_overview_shop_racing_module",
                "api.business_overview_shop_racing_monthly_module",
            ):
                await execute_sql_target(session, target)
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
async def test_postgresql_dashboard_service_operational_metrics_recomputes_time_gap_for_past_month(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": 100000,
                "monthly_total_achieved": 60000,
                "today_sales": 120,
                "monthly_achievement_rate": 60,
                "time_gap": -40,
                "estimated_gross_profit": 120,
                "estimated_expenses": 50,
                "operating_result": 70,
                "monthly_order_count": 10,
                "today_order_count": 2,
            },
            {
                "monthly_target": 159844,
                "monthly_total_achieved": 77284.41,
                "today_sales": 80,
                "monthly_achievement_rate": 48.35,
                "time_gap": -51.65,
                "estimated_gross_profit": 200,
                "estimated_expenses": 300,
                "operating_result": -100,
                "monthly_order_count": 4,
                "today_order_count": 1,
            }
        ]

    async def fake_load_target_summary(**kwargs):
        return {"target_amount": 259844, "target_quantity": 0}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", AsyncMock(return_value=None))
    result = await service.get_business_overview_operational_metrics(
        month="2026-02-01",
        platform=None,
    )

    assert result["today_sales"] == 200
    assert result["today_order_count"] == 3
    assert result["monthly_achievement_rate"] == 52.83
    assert result["time_gap"] == -47.17


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_recomputes_time_gap_for_current_month(monkeypatch):
    service = PostgresqlDashboardService()

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 9)

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": 259844,
                "monthly_total_achieved": 137284.41,
                "today_sales": 120,
                "monthly_achievement_rate": 0,
                "time_gap": -300,
                "estimated_gross_profit": 200,
                "estimated_expenses": 300,
                "operating_result": -100,
                "monthly_order_count": 10,
                "today_order_count": 2,
            }
        ]

    async def fake_load_target_summary(**kwargs):
        return {"target_amount": 259844, "target_quantity": 0}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(dashboard_service_module, "date_cls", FakeDate)
    result = await service.get_business_overview_operational_metrics(
        month="2026-06-01",
        platform=None,
    )

    assert result["monthly_achievement_rate"] == 52.83
    assert result["time_gap"] == 22.83


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_recomputes_time_gap_for_future_month(monkeypatch):
    service = PostgresqlDashboardService()

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 9)

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": 259844,
                "monthly_total_achieved": 137284.41,
                "today_sales": 120,
                "monthly_achievement_rate": 0,
                "time_gap": -300,
                "estimated_gross_profit": 200,
                "estimated_expenses": 300,
                "operating_result": -100,
                "monthly_order_count": 10,
                "today_order_count": 2,
            }
        ]

    async def fake_load_target_summary(**kwargs):
        return {"target_amount": 259844, "target_quantity": 0}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(dashboard_service_module, "date_cls", FakeDate)
    result = await service.get_business_overview_operational_metrics(
        month="2026-07-01",
        platform=None,
    )

    assert result["monthly_achievement_rate"] == 52.83
    assert result["time_gap"] == 52.83


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_returns_none_time_gap_without_achievement_rate(
    monkeypatch,
):
    service = PostgresqlDashboardService()

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 9)

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": None,
                "monthly_total_achieved": 137284.41,
                "today_sales": 120,
                "monthly_achievement_rate": None,
                "time_gap": -300,
                "estimated_gross_profit": 200,
                "estimated_expenses": 300,
                "operating_result": -100,
                "monthly_order_count": 10,
                "today_order_count": 2,
            }
        ]

    async def fake_load_target_summary(**kwargs):
        return {"target_amount": None, "target_quantity": 0}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", AsyncMock(return_value=None))
    monkeypatch.setattr(dashboard_service_module, "date_cls", FakeDate)
    result = await service.get_business_overview_operational_metrics(
        month="2026-06-01",
        platform=None,
    )

    assert result["monthly_achievement_rate"] is None
    assert result["time_gap"] is None


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_supports_shop_filter(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
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

    async def fake_load_target_summary(**kwargs):
        captured.append(("target_summary", kwargs))
        return {"target_amount": 1000, "target_quantity": 10}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)

    result = await service.get_business_overview_operational_metrics(
        month="2026-03-01",
        platform="shopee",
        shop_id="shop-1",
    )

    query, params = captured[0]
    assert result["monthly_target"] == 1000
    assert "platform_code = :platform_code" in query
    assert "shop_id = :shop_id" in query
    assert params["platform_code"] == "shopee"
    assert params["shop_id"] == "shop-1"
    assert captured[1][1]["shop_id"] == "shop-1"
    assert result["meta"]["target_source"] == "service_target_summary"
    assert "monthly_target" in result["meta"]["service_enriched_fields"]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_inventory_backlog_reads_from_api_modules(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        if "FROM api.inventory_backlog_summary_module" in query:
            return [
                {
                    "total_value": 400,
                    "backlog_30d_value": 400,
                    "backlog_60d_value": 100,
                    "backlog_90d_value": 100,
                    "total_quantity": 110,
                    "high_risk_sku_count": 1,
                    "medium_risk_sku_count": 1,
                    "low_risk_sku_count": 0,
                }
            ]
        if "FROM api.business_overview_inventory_backlog_module" in query:
            return [
                {
                    "snapshot_date": "2026-04-14",
                    "platform_code": "shopee",
                    "shop_id": "shop-a",
                    "product_id": "P2",
                    "product_name": "Beta",
                    "platform_sku": "SKU-2",
                    "product_sku": "PSKU-2",
                    "warehouse_name": "WH-1",
                    "available_stock": 10,
                    "inventory_value": 100,
                    "daily_avg_sales": 0,
                    "estimated_turnover_days": 100,
                    "stock_delta": 0,
                    "inventory_value_delta": 0,
                    "is_stagnant": True,
                    "snapshot_gap_days": 7,
                    "estimated_stagnant_days": 14,
                    "stagnant_snapshot_count": 3,
                    "risk_level": "high",
                    "clearance_priority_score": 1100,
                },
                {
                    "snapshot_date": "2026-04-14",
                    "platform_code": "shopee",
                    "shop_id": "shop-a",
                    "product_id": "P1",
                    "product_name": "Alpha",
                    "platform_sku": "SKU-1",
                    "product_sku": "PSKU-1",
                    "warehouse_name": "WH-1",
                    "available_stock": 100,
                    "inventory_value": 300,
                    "daily_avg_sales": 2.0,
                    "estimated_turnover_days": 50.0,
                    "stock_delta": -5.0,
                    "inventory_value_delta": -50.0,
                    "is_stagnant": True,
                    "snapshot_gap_days": 7,
                    "estimated_stagnant_days": 7.0,
                    "stagnant_snapshot_count": 1,
                    "risk_level": "medium",
                    "clearance_priority_score": 800,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    result = await service.get_business_overview_inventory_backlog(min_days=45, limit=20)

    assert len(captured) == 2
    summary_query, summary_params = next((query, params) for query, params in captured if "FROM api.inventory_backlog_summary_module" in query)
    rows_query, rows_params = next((query, params) for query, params in captured if "FROM api.business_overview_inventory_backlog_module" in query)
    assert "FROM mart.inventory_snapshot_latest" not in summary_query
    assert "FROM mart.inventory_snapshot_change" not in summary_query
    assert "FROM semantic.fact_orders_atomic" not in summary_query
    assert "ORDER BY clearance_priority_score DESC" in rows_query
    assert "LIMIT :limit" in rows_query
    assert rows_params == {"min_days": 45, "limit": 20}
    assert summary_params == {}

    assert result["summary"] == {
        "total_value": 400.0,
        "backlog_30d_value": 400.0,
        "backlog_60d_value": 100.0,
        "backlog_90d_value": 100.0,
        "backlog_30d_ratio": 100.0,
        "backlog_60d_ratio": 25.0,
        "backlog_90d_ratio": 25.0,
        "total_quantity": 110,
        "high_risk_sku_count": 1,
        "medium_risk_sku_count": 1,
        "low_risk_sku_count": 0,
    }
    assert [row["platform_sku"] for row in result["top_products"]] == ["SKU-2", "SKU-1"]
    assert result["top_products"][0]["rank"] == 1
    assert result["top_products"][0]["risk_level"] == "high"
    assert result["top_products"][1]["daily_avg_sales"] == 2.0
    assert result["top_products"][1]["estimated_turnover_days"] == 50.0
    assert result["top_products"][1]["stock_delta"] == -5.0
    assert result["top_products"][1]["inventory_value_delta"] == -50.0
    assert result["top_products"][1]["estimated_stagnant_days"] == 7.0
    assert result["top_products"][1]["stagnant_snapshot_count"] == 1


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_clearance_ranking_reads_from_api_module(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        if "FROM api.clearance_ranking_module" in query:
            return [
                {
                    "snapshot_date": "2026-04-14",
                    "platform_code": "shopee",
                    "shop_id": "shop-a",
                    "product_id": "P2",
                    "product_name": "Beta",
                    "platform_sku": "SKU-2",
                    "product_sku": "PSKU-2",
                    "available_stock": 10,
                    "inventory_value": 100,
                    "estimated_turnover_days": 100,
                    "daily_avg_sales": 0,
                    "estimated_stagnant_days": 14,
                    "stagnant_snapshot_count": 3,
                    "risk_level": "high",
                    "clearance_priority_score": 1100,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_clearance_ranking(min_days=45, limit=10)

    assert len(result) == 1
    query, params = captured[0]
    assert "FROM api.clearance_ranking_module" in query
    assert "FROM mart.inventory_snapshot_latest" not in query
    assert "raw_data->>" not in query
    assert "REGEXP_REPLACE" not in query
    assert "FROM b_class." not in query
    assert "ORDER BY clearance_priority_score DESC" in query
    assert "LIMIT :limit" in query
    assert params == {"min_days": 45, "limit": 10, "period_start": None, "period_end": None}
    assert result[0]["rank"] == 1
    assert result[0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_clearance_ranking_filters_by_requested_period(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return []

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    await service.get_clearance_ranking(
        min_days=45,
        limit=10,
        granularity="monthly",
        target_date="2026-04-15",
    )

    query, params = captured[0]
    assert "snapshot_date >= :period_start" in query
    assert "snapshot_date <= :period_end" in query
    assert params["min_days"] == 45
    assert params["limit"] == 10
    assert str(params["period_start"]) == "2026-04-01"
    assert str(params["period_end"]) == "2026-04-30"


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
                    CREATE TABLE a_class.sales_targets_a (
                        "年月" VARCHAR(7),
                        "店铺ID" VARCHAR(255),
                        "目标销售额" NUMERIC,
                        "目标订单数" NUMERIC,
                        "目标单量" NUMERIC
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
            if "FROM api.business_overview_comparison_platform_module" in query:
                return [
                    {
                        "period_key": "2025-09-01",
                        "sales_amount": 5000,
                        "sales_quantity": 50,
                        "traffic": 1000,
                        "conversion_rate": 5,
                        "avg_order_value": 100,
                        "attach_rate": 1.2,
                        "profit": 300,
                    }
                ]
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
                        "platform_code" VARCHAR(32),
                        "店铺ID" VARCHAR(255),
                        "年月" VARCHAR(7),
                        "租金" NUMERIC,
                        "营销费用" NUMERIC,
                        "水电费" NUMERIC,
                        "AI Token费用" NUMERIC,
                        "其他成本" NUMERIC,
                        "成本合计" NUMERIC,
                        "删除时间" TIMESTAMP
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
                    INSERT INTO a_class.operating_costs ("platform_code", "店铺ID", "年月", "租金", "营销费用", "水电费", "AI Token费用", "其他成本", "成本合计")
                    VALUES
                        ('shopee', 'shopee新加坡3C店', '2025-09', 100, 200, 300, 0, 400, 1000),
                        ('tiktok', 'Tiktok 2店', '2025-09', 100, 200, 200, 0, 300, 800)
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
            async with session_factory() as session:
                cost_row = (
                    await session.execute(
                        text(
                            """
                            SELECT "成本合计" AS total_cost, "删除时间" AS deleted_at
                            FROM a_class.operating_costs
                            WHERE "platform_code" = 'tiktok'
                              AND "店铺ID" = 'shop-1'
                              AND "年月" = '2026-03'
                            """
                        )
                    )
                ).fetchone()
            estimated_expenses = None
            if cost_row and cost_row.deleted_at is None:
                estimated_expenses = float(cost_row.total_cost or 0)
            return [
                {
                    "monthly_target": 0,
                    "monthly_total_achieved": 25000,
                    "today_sales": 1200,
                    "monthly_achievement_rate": 0,
                    "time_gap": 0,
                    "estimated_gross_profit": 3000,
                    "estimated_expenses": estimated_expenses,
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
        assert result["monthly_total_achieved"] == 25000

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_operational_metrics_respects_soft_deleted_expenses(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.postgres import PostgresContainer
    from urllib.parse import urlparse, urlunparse
    from datetime import datetime, timezone

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
                    CREATE TABLE a_class.sales_targets_a (
                        "年月" VARCHAR(7),
                        "店铺ID" VARCHAR(255),
                        "目标销售额" NUMERIC,
                        "目标订单数" NUMERIC,
                        "目标单量" NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE a_class.operating_costs (
                        "platform_code" VARCHAR(32),
                        "店铺ID" VARCHAR(255),
                        "年月" VARCHAR(7),
                        "租金" NUMERIC,
                        "营销费用" NUMERIC,
                        "水电费" NUMERIC,
                        "AI Token费用" NUMERIC,
                        "其他成本" NUMERIC,
                        "成本合计" NUMERIC,
                        "删除时间" TIMESTAMPTZ,
                        "删除人" BIGINT
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
            async with session_factory() as session:
                cost_row = (
                    await session.execute(
                        text(
                            """
                            SELECT "成本合计" AS total_cost, "删除时间" AS deleted_at
                            FROM a_class.operating_costs
                            WHERE "platform_code" = 'tiktok'
                              AND "店铺ID" = 'shop-1'
                              AND "年月" = '2026-03'
                            """
                        )
                    )
                ).fetchone()
            estimated_expenses = None
            if cost_row and cost_row.deleted_at is None:
                estimated_expenses = float(cost_row.total_cost or 0)
            return [
                {
                    "monthly_target": 0,
                    "monthly_total_achieved": 25000,
                    "today_sales": 1200,
                    "monthly_achievement_rate": 0,
                    "time_gap": 0,
                    "estimated_gross_profit": 3000,
                    "estimated_expenses": estimated_expenses,
                    "operating_result": 0,
                    "monthly_order_count": 200,
                    "today_order_count": 12,
                }
            ]

        monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.operating_costs
                        ("platform_code", "店铺ID", "年月", "租金", "营销费用", "水电费", "AI Token费用", "其他成本", "成本合计", "删除时间", "删除人")
                    VALUES
                        ('tiktok', 'shop-1', '2026-03', 10, 60, 5, 6, 30, 111, NULL, NULL)
                    """
                )
            )
            await session.commit()

        before = await service.get_business_overview_operational_metrics(
            month="2026-03-01",
            platform="tiktok",
        )
        assert before["estimated_expenses"] == 111

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE a_class.operating_costs
                    SET "删除时间" = :deleted_at,
                        "删除人" = 1
                    WHERE "platform_code" = 'tiktok'
                      AND "店铺ID" = 'shop-1'
                      AND "年月" = '2026-03'
                    """
                ),
                {"deleted_at": datetime.now(timezone.utc)},
            )
            await session.commit()

        after_delete = await service.get_business_overview_operational_metrics(
            month="2026-03-01",
            platform="tiktok",
        )
        assert after_delete["estimated_expenses"] is None

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE a_class.operating_costs
                    SET "删除时间" = NULL,
                        "删除人" = NULL
                    WHERE "platform_code" = 'tiktok'
                      AND "店铺ID" = 'shop-1'
                      AND "年月" = '2026-03'
                    """
                )
            )
            await session.commit()

        after_restore = await service.get_business_overview_operational_metrics(
            month="2026-03-01",
            platform="tiktok",
        )
        assert after_restore["estimated_expenses"] == 111

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


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_load_target_summary_monthly_platform_prefers_period_scoped_shop_rows(monkeypatch):
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
                        1, '2026-04 target', 'shop', DATE '2026-04-01', DATE '2026-04-30',
                        400000, 3000, 0, 0, 0, 'active'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO a_class.target_breakdown (
                        target_id, breakdown_type, platform_code, shop_id, period_start, period_end,
                        target_amount, target_quantity
                    ) VALUES
                        (1, 'shop', 'shopee', 'shop-1', NULL, NULL, 273520, 2041),
                        (1, 'shop', 'shopee', 'shop-1', DATE '2026-04-01', DATE '2026-04-30', 273520, 2041),
                        (1, 'shop', 'tiktok', 'shop-2', NULL, NULL, 126480, 959),
                        (1, 'shop', 'tiktok', 'shop-2', DATE '2026-04-01', DATE '2026-04-30', 126480, 959)
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
            granularity="monthly",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            platform="shopee",
        )

        assert result["target_amount"] == 273520
        assert result["target_quantity"] == 2041

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


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_traffic_ranking_uses_page_views_as_primary_traffic(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "shop-a",
                "visitor_count": 100,
                "page_views": 120,
                "order_count": 3,
                "conversion_rate": 1.0,
                "uv_conversion_rate": 3.0,
                "pv_conversion_rate": 2.5,
            },
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "shop-b",
                "visitor_count": 50,
                "page_views": 180,
                "order_count": 6,
                "conversion_rate": 1.0,
                "uv_conversion_rate": 12.0,
                "pv_conversion_rate": 3.33,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_traffic_ranking(
        granularity="monthly",
        target_date="2026-03-01",
        dimension="shop",
    )

    assert result[0]["name"] == "shop-b"
    assert result[0]["page_views"] == 180
    assert result[0]["order_count"] == 6
    assert result[0]["uv_conversion_rate"] == 12.0
    assert result[0]["pv_conversion_rate"] == 3.33
    assert result[1]["name"] == "shop-a"
    assert len(captured) == 1
    assert "FROM api.business_overview_traffic_ranking_module" in captured[0][0]
    assert "src.order_count" in captured[0][0]
    assert "src.uv_conversion_rate" in captured[0][0]
    assert "src.pv_conversion_rate" in captured[0][0]


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_traffic_ranking_prefers_resolved_display_name(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200830",
                "display_name": "Singapore(HX Home)",
                "visitor_count": 0,
                "page_views": 31,
                "conversion_rate": 0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_traffic_ranking(
        granularity="monthly",
        target_date="2026-03-01",
        dimension="shop",
    )

    assert result[0]["name"] == "Singapore(HX Home)"


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_traffic_ranking_returns_previous_period_changes(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[tuple[str, dict[str, object]]] = []

    async def fake_fetch_rows(query, params):
        captured.append((query, params))
        return [
            {
                "granularity": "daily",
                "period_key": date(2026, 5, 10),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "visitor_count": 120,
                "page_views": 260,
                "order_count": 12,
                "uv_conversion_rate": 10,
                "pv_conversion_rate": 4.62,
            },
            {
                "granularity": "daily",
                "period_key": date(2026, 5, 9),
                "platform_code": "tiktok",
                "shop_id": "shop-a",
                "visitor_count": 100,
                "page_views": 200,
                "order_count": 8,
                "uv_conversion_rate": 8,
                "pv_conversion_rate": 4,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_traffic_ranking(
        granularity="daily",
        target_date="2026-05-10",
        dimension="shop",
    )

    assert result[0]["visitor_count_previous"] == 100
    assert result[0]["page_views_previous"] == 200
    assert result[0]["uv_conversion_rate_previous"] == 8
    assert result[0]["pv_conversion_rate_previous"] == 4
    assert result[0]["visitor_count_change_rate"] == 20
    assert result[0]["page_views_change_rate"] == 30
    assert result[0]["uv_conversion_rate_change_value"] == 2
    assert result[0]["pv_conversion_rate_change_value"] == 0.62
    assert captured[0][1]["period_key"] == date(2026, 5, 10)
    assert captured[0][1]["previous_period_key"] == date(2026, 5, 9)
    assert "src.period_key IN (:period_key, :previous_period_key)" in captured[0][0]


@pytest.mark.asyncio
async def test_business_overview_shop_and_traffic_queries_share_display_identity_join(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[str] = []

    async def fake_fetch_rows(query, params):
        captured.append(query)
        return []

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    await service.get_business_overview_shop_racing(
        granularity="monthly",
        target_date="2026-03-01",
        group_by="shop",
    )
    await service.get_business_overview_traffic_ranking(
        granularity="monthly",
        target_date="2026-03-01",
        dimension="shop",
    )

    assert len(captured) == 2
    for query in captured:
        assert "LOWER(COALESCE(ds.platform_code, '')) = LOWER(COALESCE(src.platform_code, ''))" in query
        assert "COALESCE(sa.platform_shop_id, '') = COALESCE(src.shop_id, '')" in query
        assert "sa.id::text = COALESCE(src.shop_id, '')" in query
        assert "AS account_display_name" in query


@pytest.mark.asyncio
async def test_postgresql_dashboard_service_traffic_ranking_account_group_uses_shop_account_hierarchy(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200830",
                "display_name": "Singapore(HX Home)",
                "shop_account_id": "shopee_sg_hx_home",
                "account_display_name": "Main SG / HX Home",
                "main_account_id": "main_shopee_sg",
                "main_account_name": "Main SG",
                "visitor_count": 100,
                "page_views": 400,
                "order_count": 1,
                "conversion_rate": 0,
                "uv_conversion_rate": 1.0,
                "pv_conversion_rate": 0.25,
            },
            {
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": "shopee",
                "shop_id": "1308200831",
                "display_name": "Singapore(HX Annex)",
                "shop_account_id": "shopee_sg_hx_home",
                "account_display_name": "Main SG / HX Home",
                "main_account_id": "main_shopee_sg",
                "main_account_name": "Main SG",
                "visitor_count": 50,
                "page_views": 100,
                "order_count": 5,
                "conversion_rate": 0,
                "uv_conversion_rate": 10.0,
                "pv_conversion_rate": 5.0,
            },
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_business_overview_traffic_ranking(
        granularity="monthly",
        target_date="2026-03-01",
        dimension="account",
    )

    assert len(result) == 1
    assert result[0]["name"] == "Main SG / HX Home"
    assert result[0]["shop_account_id"] == "shopee_sg_hx_home"
    assert result[0]["main_account_id"] == "main_shopee_sg"
    assert result[0]["visitor_count"] == 150
    assert result[0]["page_views"] == 500
    assert result[0]["order_count"] == 6
    assert result[0]["uv_conversion_rate"] == 4.0
    assert result[0]["pv_conversion_rate"] == 1.2


@pytest.mark.asyncio
async def test_store_analysis_traffic_summary_uses_page_views_per_visitor_instead_of_conversion_rate(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "period_start": "2026-03-01",
                "period_end": "2026-03-01",
                "visitor_count": 50,
                "page_views": 100,
                "conversion_rate": 999,
                "page_views_per_visitor": 2.0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    result = await service.get_store_analysis_traffic_summary(
        platform="shopee",
        shop_id="shop-a",
        granularity="daily",
        target_date="2026-03-01",
    )

    assert result["visitor_count"] == 50
    assert result["page_views"] == 100
    assert result["conversion_rate"] is None
    assert result["page_views_per_visitor"] == 2.0


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_monthly_kpi_does_not_fallback_from_daily(monkeypatch):
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
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS semantic"))
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        shop_account_id VARCHAR(100) NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        store_name VARCHAR(200) NOT NULL,
                        platform_shop_id VARCHAR(256)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_account_aliases (
                        id SERIAL PRIMARY KEY,
                        shop_account_id INTEGER NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        alias_value VARCHAR(200) NOT NULL,
                        alias_normalized VARCHAR(200) NOT NULL,
                        is_primary BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE
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
                        page_views NUMERIC,
                        impressions NUMERIC
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_shopee_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_tiktok_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_miaoshou_orders_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_shopee_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_tiktok_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS b_class.fact_miaoshou_analytics_monthly (
                        platform_code VARCHAR(32),
                        shop_id VARCHAR(256),
                        metric_date DATE,
                        raw_data JSONB,
                        data_hash VARCHAR(128),
                        ingest_timestamp TIMESTAMP
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"order_id":"o-1","paid_amount":"100","product_quantity":"12","profit":"30"}'::jsonb,
                        'month-order-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_analytics_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"visitor_count":"200","page_views":"300","impressions":"1000"}'::jsonb,
                        'month-analytics-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.commit()

            async with session_factory() as session:
                for target in (
                    "mart.shop_day_kpi",
                    "mart.shop_week_kpi",
                    "semantic.shop_identity_resolution_candidates",
                    "semantic.fact_orders_monthly_atomic_mv",
                    "semantic.fact_orders_monthly_atomic",
                    "semantic.fact_analytics_monthly_atomic_mv",
                    "semantic.fact_analytics_monthly_atomic",
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
            async def fake_load_active_employee_count(_period_key):
                return 0

            monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)
            result = await service.get_business_overview_kpi("2026-03-01", None)

        assert result["gmv"] == 100
        assert result["order_count"] == 1
        assert result["visitor_count"] == 200
        assert result["page_views"] == 300
        assert result["uv_conversion_rate"] == 0.5
        assert result["pv_conversion_rate"] == 0.33
        assert result["avg_order_value"] == 100
        assert result["attach_rate"] == 12

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgresql_dashboard_service_monthly_kpi_keeps_pv_and_uv_separate(monkeypatch):
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
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        shop_account_id VARCHAR(100) NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        store_name VARCHAR(200) NOT NULL,
                        platform_shop_id VARCHAR(256)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_account_aliases (
                        id SERIAL PRIMARY KEY,
                        shop_account_id INTEGER NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        alias_value VARCHAR(200) NOT NULL,
                        alias_normalized VARCHAR(200) NOT NULL,
                        is_primary BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                    """
                )
            )
            for table_name in (
                "b_class.fact_shopee_orders_monthly",
                "b_class.fact_tiktok_orders_monthly",
                "b_class.fact_miaoshou_orders_monthly",
                "b_class.fact_shopee_analytics_monthly",
                "b_class.fact_tiktok_analytics_monthly",
                "b_class.fact_miaoshou_analytics_monthly",
            ):
                await session.execute(
                    text(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            platform_code VARCHAR(32),
                            shop_id VARCHAR(256),
                            metric_date DATE,
                            raw_data JSONB,
                            data_hash VARCHAR(128),
                            ingest_timestamp TIMESTAMP
                        )
                        """
                    )
                )

            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"order_id":"shopee-order-1","paid_amount":"100","product_quantity":"1","profit":"20"}'::jsonb,
                        'shopee-order-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_tiktok_orders_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'tiktok', 'shop-b', DATE '2026-03-01',
                        '{"order_id":"tiktok-order-1","paid_amount":"200","product_quantity":"2","profit":"50"}'::jsonb,
                        'tiktok-order-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_analytics_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"页面浏览数":"300"}'::jsonb,
                        'shopee-analytics-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_tiktok_analytics_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    )
                    VALUES (
                        'tiktok', 'shop-b', DATE '2026-03-01',
                        '{"页面浏览次数":"80"}'::jsonb,
                        'tiktok-analytics-1', TIMESTAMP '2026-03-01 10:00:00'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            for target in (
                "semantic.shop_identity_resolution_candidates",
                "semantic.fact_orders_monthly_atomic_mv",
                "semantic.fact_orders_monthly_atomic",
                "semantic.fact_analytics_monthly_atomic_mv",
                "semantic.fact_analytics_monthly_atomic",
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
            async def fake_load_active_employee_count(_period_key):
                return 0

            monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)
            result = await service.get_business_overview_kpi("2026-03-01", None)

        assert result["gmv"] == 300
        assert result["order_count"] == 2
        assert result["visitor_count"] is None
        assert result["page_views"] == 380
        assert result["impressions"] is None
        assert result["conversion_rate"] is None
        assert result["uv_conversion_rate"] is None
        assert result["pv_conversion_rate"] == 0.53
        assert result["visit_rate"] is None

        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_business_overview_kpi_module_exposes_pv_uv_conversion_rates():
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
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            await session.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.platform_accounts (
                        id SERIAL PRIMARY KEY,
                        account_id VARCHAR(100) NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        account_alias VARCHAR(200),
                        store_name VARCHAR(200) NOT NULL,
                        shop_id VARCHAR(256)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_accounts (
                        id SERIAL PRIMARY KEY,
                        platform VARCHAR(50),
                        store_name VARCHAR(200),
                        platform_shop_id VARCHAR(256),
                        shop_account_id VARCHAR(256)
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS core.shop_account_aliases (
                        id SERIAL PRIMARY KEY,
                        shop_account_id INTEGER,
                        platform VARCHAR(50),
                        alias_value VARCHAR(256),
                        alias_normalized VARCHAR(256),
                        is_active BOOLEAN DEFAULT TRUE,
                        is_primary BOOLEAN DEFAULT FALSE
                    )
                    """
                )
            )
            for table_name in (
                "b_class.fact_shopee_orders_monthly",
                "b_class.fact_tiktok_orders_monthly",
                "b_class.fact_miaoshou_orders_monthly",
                "b_class.fact_shopee_analytics_monthly",
                "b_class.fact_tiktok_analytics_monthly",
                "b_class.fact_miaoshou_analytics_monthly",
            ):
                await session.execute(
                    text(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            platform_code VARCHAR(32),
                            shop_id VARCHAR(256),
                            metric_date DATE,
                            raw_data JSONB,
                            data_hash VARCHAR(128),
                            ingest_timestamp TIMESTAMP
                        )
                        """
                    )
                )

            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_orders_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"order_id":"month-1","paid_amount":"500","product_quantity":"5","profit":"50"}'::jsonb,
                        'month-order-1', TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO b_class.fact_shopee_analytics_monthly (
                        platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
                    ) VALUES (
                        'shopee', 'shop-a', DATE '2026-03-01',
                        '{"visitor_count":"200","page_views":"300","impressions":"1000"}'::jsonb,
                        'month-traffic-1', TIMESTAMP '2026-03-02 10:00:00'
                    )
                    """
                )
            )
            await session.commit()

        async with session_factory() as session:
            for target in (
                "semantic.shop_identity_resolution_candidates",
                "semantic.fact_orders_monthly_atomic_mv",
                "semantic.fact_orders_monthly_atomic",
                "semantic.fact_analytics_monthly_atomic_mv",
                "semantic.fact_analytics_monthly_atomic",
                "mart.platform_month_kpi",
                "api.business_overview_kpi_module",
            ):
                await execute_sql_target(session, target)
            await session.commit()

            row = (
                await session.execute(
                    text(
                        """
                        SELECT visitor_count, page_views, impressions, conversion_rate, uv_conversion_rate, pv_conversion_rate, visit_rate
                        FROM api.business_overview_kpi_module
                        WHERE period_month = DATE '2026-03-01'
                          AND platform_code = 'shopee'
                        """
                    )
                )
            ).fetchone()

            assert row[0] == 200
            assert row[1] == 300
            assert row[2] == 1000
            assert float(row[3]) == 0.5
            assert float(row[4]) == 0.5
            assert float(row[5]) == 0.33
            assert float(row[6]) == 20.0

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
                "mart.inventory_snapshot_history",
                "mart.inventory_snapshot_latest",
                "mart.inventory_snapshot_change",
                "mart.inventory_current",
                "mart.inventory_backlog_base",
                "api.business_overview_inventory_backlog_module",
                "api.inventory_backlog_summary_module",
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

        assert "summary" in backlog
        assert "top_products" in backlog
        assert len(backlog["top_products"]) == 1
        assert backlog["top_products"][0]["platform_code"] == "shopee"
        assert backlog["top_products"][0]["rank"] == 1
        assert "risk_level" in backlog["top_products"][0]
        assert len(clearance) == 1
        assert clearance[0]["platform_code"] == "shopee"
        assert clearance[0]["estimated_turnover_days"] >= 30

        await engine.dispose()
