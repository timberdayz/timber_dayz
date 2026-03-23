from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)


def test_refresh_registry_includes_remaining_dashboard_api_targets():
    expected_targets = {
        "api.business_overview_shop_racing_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_operational_metrics_module",
    }

    assert expected_targets.issubset(PIPELINE_DEPENDENCIES.keys())
    assert expected_targets.issubset(SQL_TARGET_PATHS.keys())
