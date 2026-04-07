import pytest

from backend.services.postgresql_dashboard_service import (
    PostgresqlDashboardService,
    reduce_annual_summary_kpi_rows,
    reduce_business_overview_comparison_rows,
    reduce_business_overview_kpi_rows,
)


def test_reduce_business_overview_kpi_rows_preserves_missing_visitor_count():
    result = reduce_business_overview_kpi_rows(
        [
            {
                "gmv": 100,
                "order_count": 10,
                "visitor_count": None,
                "total_items": 12,
                "profit": 30,
            }
        ]
    )

    assert result["visitor_count"] is None
    assert result["conversion_rate"] is None


def test_reduce_business_overview_comparison_rows_preserves_missing_metrics():
    result = reduce_business_overview_comparison_rows(
        current_row={
            "sales_amount": 300,
            "sales_quantity": 30,
            "traffic": None,
            "conversion_rate": None,
            "avg_order_value": 10,
            "attach_rate": 1.2,
            "profit": 90,
            "target_sales_amount": None,
            "target_sales_quantity": None,
        },
        previous_row={
            "sales_amount": 240,
            "sales_quantity": 24,
            "traffic": 480,
            "conversion_rate": 5,
            "avg_order_value": 10,
            "attach_rate": 1.1,
            "profit": 72,
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

    assert result["metrics"]["traffic"]["today"] is None
    assert result["metrics"]["conversion_rate"]["today"] is None
    assert result["target"]["sales_amount"] is None
    assert result["target"]["achievement_rate"] is None


def test_reduce_annual_summary_kpi_rows_preserves_missing_total_cost():
    result = reduce_annual_summary_kpi_rows(
        [
            {"gmv": 100, "total_cost": None, "profit": 20},
        ]
    )

    assert result["total_cost"] is None
    assert result["net_margin"] is None
    assert result["roi"] is None


@pytest.mark.asyncio
async def test_operational_metrics_aggregation_preserves_missing_values(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        return [
            {
                "monthly_target": None,
                "monthly_total_achieved": 800,
                "today_sales": None,
                "monthly_achievement_rate": None,
                "time_gap": None,
                "estimated_gross_profit": 200,
                "estimated_expenses": None,
                "operating_result": None,
                "monthly_order_count": 10,
                "today_order_count": None,
            }
        ]

    async def fake_load_target_summary(granularity, period_start, period_end, platform=None):
        return {"target_amount": None, "target_quantity": None}

    async def fake_load_operating_expenses_summary(period_month):
        return None

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", fake_load_operating_expenses_summary)

    result = await service.get_business_overview_operational_metrics(
        month="2026-03-01",
        platform=None,
    )

    assert result["monthly_target"] is None
    assert result["today_sales"] is None
    assert result["estimated_expenses"] is None
    assert result["operating_result"] is None
    assert result["today_order_count"] is None


@pytest.mark.asyncio
async def test_comparison_service_preserves_missing_target_summary_values(monkeypatch):
    service = PostgresqlDashboardService()

    async def fake_fetch_rows(query, params):
        if "business_overview_comparison_module" in query:
            period_key = params.get("period_key")
            if str(period_key) == "2026-04-01":
                return [
                    {
                        "sales_amount": 5000,
                        "sales_quantity": 50,
                        "traffic": 1000,
                        "conversion_rate": 5,
                        "avg_order_value": 100,
                        "attach_rate": None,
                        "profit": 300,
                        "target_sales_amount": None,
                        "target_sales_quantity": None,
                    }
                ]
        return []

    async def fake_load_target_summary(granularity, period_start, period_end, platform=None):
        return {"target_amount": None, "target_quantity": None}

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)

    result = await service.get_business_overview_comparison(
        granularity="monthly",
        target_date="2026-04-01",
        platform=None,
    )

    assert result["metrics"]["sales_amount"]["today"] == 5000
    assert result["target"]["sales_amount"] is None
    assert result["target"]["sales_quantity"] is None
    assert result["target"]["achievement_rate"] == 0
