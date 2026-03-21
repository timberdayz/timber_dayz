from backend.services.postgresql_dashboard_service import (
    PostgresqlDashboardService,
    get_postgresql_dashboard_service,
    rank_inventory_backlog_rows,
    reduce_annual_summary_kpi_rows,
    reduce_business_overview_comparison_rows,
    reduce_business_overview_kpi_rows,
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
