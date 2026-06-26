from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)


def test_refresh_registry_includes_remaining_dashboard_api_targets():
    expected_targets = {
        "api.business_overview_shop_racing_module",
        "api.business_overview_shop_racing_monthly_module",
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


def test_expand_downstream_targets_includes_all_order_dashboard_dependents():
    from backend.services.data_pipeline.refresh_registry import expand_downstream_targets

    targets = expand_downstream_targets(
        [
            "semantic.fact_orders_atomic",
            "semantic.fact_orders_monthly_atomic_mv",
        ]
    )

    expected_targets = {
        "semantic.fact_orders_atomic",
        "semantic.fact_orders_monthly_atomic_mv",
        "semantic.fact_orders_monthly_atomic",
        "mart.shop_day_kpi",
        "mart.shop_week_kpi",
        "mart.shop_month_kpi",
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "mart.platform_month_kpi",
        "api.business_overview_kpi_module",
        "api.business_overview_comparison_module",
        "api.business_overview_comparison_platform_module",
        "api.business_overview_shop_racing_module",
        "api.business_overview_shop_racing_monthly_module",
        "api.business_overview_inventory_backlog_module",
    }

    assert expected_targets.issubset(set(targets))
    assert targets.index("semantic.fact_orders_atomic") < targets.index("mart.platform_day_kpi")
    assert targets.index("mart.platform_day_kpi") < targets.index(
        "api.business_overview_comparison_platform_module"
    )


def test_resolve_refresh_targets_for_shopee_orders_monthly_expands_cascade_dependents():
    from backend.services.data_pipeline.refresh_registry import resolve_refresh_targets_for_source_table

    targets = resolve_refresh_targets_for_source_table(
        source_table_name="fact_shopee_orders_monthly",
        data_domain="orders",
        granularity="monthly",
    )

    expected_targets = {
        "semantic.fact_orders_atomic",
        "semantic.fact_orders_monthly_atomic_mv",
        "semantic.fact_orders_monthly_atomic",
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "api.business_overview_comparison_platform_module",
        "api.business_overview_shop_racing_monthly_module",
    }

    assert expected_targets.issubset(set(targets))


def test_resolve_refresh_targets_for_traffic_alias_uses_analytics_pipeline():
    from backend.services.data_pipeline.refresh_registry import resolve_refresh_targets_for_source_table

    targets = resolve_refresh_targets_for_source_table(
        source_table_name="fact_shopee_traffic_monthly",
        data_domain="traffic",
        granularity="monthly",
    )

    assert "semantic.fact_analytics_atomic" in targets
    assert "semantic.fact_analytics_monthly_atomic_mv" in targets
    assert "api.business_overview_traffic_ranking_module" in targets


def test_resolve_refresh_targets_for_unknown_source_table_returns_empty_list():
    from backend.services.data_pipeline.refresh_registry import resolve_refresh_targets_for_source_table

    assert (
        resolve_refresh_targets_for_source_table(
            source_table_name="fact_unknown_domain_monthly",
            data_domain="unknown",
            granularity="monthly",
        )
        == []
    )
