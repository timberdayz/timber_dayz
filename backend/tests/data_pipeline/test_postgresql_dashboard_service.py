from backend.services.postgresql_dashboard_service import (
    PostgresqlDashboardService,
    get_postgresql_dashboard_service,
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
