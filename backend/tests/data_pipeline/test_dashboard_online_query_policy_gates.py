import pytest

from backend.services.postgresql_dashboard_service import PostgresqlDashboardService


@pytest.mark.asyncio
async def test_dashboard_online_query_policy_forbids_raw_sources(monkeypatch):
    """
    This gate is intentionally broad: once a dashboard endpoint has a stable `api.*`
    read model, online request-time reads must not fall back to raw persistence or
    semantic atomic facts.
    """

    service = PostgresqlDashboardService()
    captured: list[str] = []

    async def fake_fetch_rows(query, params):
        captured.append(str(query))
        query_text = str(query)

        if "COUNT(1) AS total FROM api.b_cost_analysis_order_detail_module" in query_text:
            return [{"total": 0}]

        if "FROM api.business_overview_kpi_module" in query_text:
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

        return []

    async def fake_fetch_rows_with_statement_timeout(query, params, *_args, **_kwargs):
        return await fake_fetch_rows(query, params)

    async def fake_load_active_employee_count(_period_key):
        return 0

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_fetch_rows_with_statement_timeout", fake_fetch_rows_with_statement_timeout)
    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)

    # Business overview + clearance (homepage/secondary)
    await service.get_business_overview_kpi(month="2026-04-01", platform=None)
    await service.get_business_overview_comparison(granularity="monthly", target_date="2026-04-01", platform=None)
    await service.get_business_overview_operational_metrics(month="2026-04-01", platform=None)
    await service.get_business_overview_traffic_ranking(granularity="monthly", target_date="2026-04-01", dimension="pv", platform=None)
    await service.get_business_overview_inventory_backlog(min_days=45, limit=20, granularity="monthly", target_date="2026-04-01")
    await service.get_clearance_ranking(min_days=45, limit=10, granularity="monthly", target_date="2026-04-01")

    # Store analysis
    await service.get_store_analysis_capabilities(platform="shopee", shop_id="shop-a")
    await service.get_store_analysis_shops(platform="shopee")
    await service.get_store_analysis_overview(
        platform="shopee",
        shop_id="shop-a",
        granularity="monthly",
        target_date="2026-04-01",
    )
    await service.get_store_analysis_traffic_summary(
        platform="shopee",
        shop_id="shop-a",
        granularity="monthly",
        target_date="2026-04-01",
    )
    await service.get_store_analysis_traffic_trend(
        platform="shopee",
        shop_id="shop-a",
        granularity="monthly",
        target_date="2026-04-01",
    )

    # Cost analysis
    await service.get_b_cost_analysis_overview(period_month="2026-04-01", platform=None, shop_id=None)
    await service.get_b_cost_analysis_shop_month(period_month="2026-04-01", platform=None, shop_id=None)
    await service.get_b_cost_analysis_order_detail(
        period_month="2026-04-01",
        platform=None,
        shop_id=None,
        page=1,
        page_size=20,
    )

    # Annual summary
    await service.get_annual_summary_kpi(granularity="monthly", period="2026-04-01")
    await service.get_annual_summary_trend(granularity="monthly", period="2026-04-01")
    await service.get_annual_summary_platform_share(granularity="monthly", period="2026-04-01")
    await service.get_annual_summary_by_shop(granularity="monthly", period="2026-04-01")

    forbidden = (
        "raw_data->>",
        "REGEXP_REPLACE",
        "FROM b_class.",
        "FROM semantic.fact_",
    )
    for query in captured:
        for token in forbidden:
            assert token not in query
