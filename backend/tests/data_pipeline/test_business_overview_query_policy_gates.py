import pytest

from backend.services.postgresql_dashboard_service import PostgresqlDashboardService


@pytest.mark.asyncio
async def test_business_overview_online_query_policy_forbids_raw_json_parsing(monkeypatch):
    service = PostgresqlDashboardService()
    captured: list[str] = []

    async def fake_fetch_rows(query, params):
        captured.append(str(query))
        if "FROM api.business_overview_kpi_module" in query:
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

    async def fake_load_target_summary(*_args, **_kwargs):
        return {"target_amount": 0.0, "target_quantity": 0.0}

    async def fake_load_operating_expenses_summary(_period_month):
        return None

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(service, "_fetch_rows_with_statement_timeout", fake_fetch_rows_with_statement_timeout)
    monkeypatch.setattr(service, "_load_active_employee_count", fake_load_active_employee_count)
    monkeypatch.setattr(service, "_load_target_summary", fake_load_target_summary)
    monkeypatch.setattr(service, "_load_operating_expenses_summary", fake_load_operating_expenses_summary)

    await service.get_business_overview_kpi(month="2026-04-01", platform=None)
    await service.get_business_overview_comparison(granularity="monthly", target_date="2026-04-01", platform=None)
    await service.get_business_overview_operational_metrics(month="2026-04-01", platform=None)
    await service.get_business_overview_traffic_ranking(granularity="monthly", target_date="2026-04-01", dimension="pv", platform=None)
    await service.get_clearance_ranking(min_days=45, limit=10, granularity="monthly", target_date="2026-04-01")

    forbidden = ("raw_data->>", "REGEXP_REPLACE", "FROM b_class.", "FROM semantic.fact_orders_atomic")
    for query in captured:
        for token in forbidden:
            assert token not in query

    assert any("FROM api.business_overview_kpi_module" in query for query in captured)
    assert any("FROM api.business_overview_traffic_ranking_module" in query for query in captured)
    assert any("FROM api.clearance_ranking_module" in query for query in captured)
