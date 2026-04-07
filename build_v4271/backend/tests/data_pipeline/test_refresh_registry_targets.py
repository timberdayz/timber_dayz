from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)


def test_refresh_registry_includes_remaining_dashboard_api_targets():
    expected_targets = {
        "api.business_overview_shop_racing_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_operational_metrics_module",
        "api.b_cost_analysis_overview_module",
    }

    assert expected_targets.issubset(PIPELINE_DEPENDENCIES.keys())
    assert expected_targets.issubset(SQL_TARGET_PATHS.keys())


def test_refresh_registry_includes_b_cost_analysis_targets():
    expected_targets = {
        "mart.b_cost_shop_month",
        "api.b_cost_analysis_shop_month_module",
        "api.b_cost_analysis_overview_module",
        "api.b_cost_analysis_order_detail_module",
    }

    assert expected_targets.issubset(PIPELINE_DEPENDENCIES.keys())
    assert expected_targets.issubset(SQL_TARGET_PATHS.keys())
