from __future__ import annotations


PIPELINE_DEPENDENCIES: dict[str, list[str]] = {
    "semantic.fact_orders_atomic": [],
    "semantic.fact_analytics_atomic": [],
    "semantic.fact_products_atomic": [],
    "semantic.fact_inventory_snapshot": [],
    "semantic.fact_services_atomic": [],
    "mart.shop_day_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.shop_week_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.shop_month_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.platform_month_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.product_day_kpi": ["semantic.fact_products_atomic"],
    "mart.inventory_snapshot_history": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_snapshot_latest": ["mart.inventory_snapshot_history"],
    "mart.inventory_snapshot_change": ["mart.inventory_snapshot_history"],
    "mart.inventory_current": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_backlog_base": ["mart.inventory_snapshot_latest", "mart.inventory_snapshot_change", "semantic.fact_orders_atomic"],
    "mart.hr_shop_monthly_profit": ["semantic.fact_orders_atomic"],
    "mart.b_cost_shop_month": ["semantic.fact_orders_atomic"],
    "mart.annual_summary_shop_month": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "api.business_overview_kpi_module": ["mart.shop_month_kpi"],
    "api.business_overview_comparison_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.business_overview_shop_racing_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.business_overview_traffic_ranking_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.business_overview_inventory_backlog_module": ["mart.inventory_backlog_base"],
    "api.inventory_backlog_summary_module": ["mart.inventory_backlog_base"],
    "api.business_overview_operational_metrics_module": ["mart.shop_month_kpi"],
    "api.b_cost_analysis_overview_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_shop_month_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_order_detail_module": ["semantic.fact_orders_atomic"],
    "api.clearance_ranking_module": ["mart.inventory_backlog_base", "api.inventory_backlog_summary_module"],
    "api.annual_summary_kpi_module": ["mart.annual_summary_shop_month"],
    "api.annual_summary_trend_module": ["mart.annual_summary_shop_month"],
    "api.annual_summary_platform_share_module": ["mart.annual_summary_shop_month"],
    "api.annual_summary_by_shop_module": ["mart.annual_summary_shop_month"],
}

SQL_TARGET_PATHS: dict[str, str] = {
    "semantic.fact_orders_atomic": "sql/semantic/orders_atomic.sql",
    "semantic.fact_analytics_atomic": "sql/semantic/analytics_atomic.sql",
    "semantic.fact_products_atomic": "sql/semantic/products_atomic.sql",
    "semantic.fact_inventory_snapshot": "sql/semantic/inventory_snapshot.sql",
    "semantic.fact_services_atomic": "sql/semantic/services_atomic.sql",
    "mart.shop_day_kpi": "sql/mart/shop_day_kpi.sql",
    "mart.shop_week_kpi": "sql/mart/shop_week_kpi.sql",
    "mart.shop_month_kpi": "sql/mart/shop_month_kpi.sql",
    "mart.platform_month_kpi": "sql/mart/platform_month_kpi.sql",
    "mart.product_day_kpi": "sql/mart/product_day_kpi.sql",
    "mart.inventory_snapshot_history": "sql/mart/inventory_snapshot_history.sql",
    "mart.inventory_snapshot_latest": "sql/mart/inventory_snapshot_latest.sql",
    "mart.inventory_snapshot_change": "sql/mart/inventory_snapshot_change.sql",
    "mart.inventory_current": "sql/mart/inventory_current.sql",
    "mart.inventory_backlog_base": "sql/mart/inventory_backlog_base.sql",
    "mart.b_cost_shop_month": "sql/mart/b_cost_shop_month.sql",
    "mart.annual_summary_shop_month": "sql/mart/annual_summary_shop_month.sql",
    "api.business_overview_kpi_module": "sql/api_modules/business_overview_kpi_module.sql",
    "api.business_overview_comparison_module": "sql/api_modules/business_overview_comparison_module.sql",
    "api.business_overview_shop_racing_module": "sql/api_modules/business_overview_shop_racing_module.sql",
    "api.business_overview_traffic_ranking_module": "sql/api_modules/business_overview_traffic_ranking_module.sql",
    "api.business_overview_inventory_backlog_module": "sql/api_modules/business_overview_inventory_backlog_module.sql",
    "api.inventory_backlog_summary_module": "sql/api_modules/inventory_backlog_summary_module.sql",
    "api.business_overview_operational_metrics_module": "sql/api_modules/business_overview_operational_metrics_module.sql",
    "api.b_cost_analysis_overview_module": "sql/api_modules/b_cost_analysis_overview_module.sql",
    "api.b_cost_analysis_shop_month_module": "sql/api_modules/b_cost_analysis_shop_month_module.sql",
    "api.b_cost_analysis_order_detail_module": "sql/api_modules/b_cost_analysis_order_detail_module.sql",
    "api.clearance_ranking_module": "sql/api_modules/clearance_ranking_module.sql",
    "api.annual_summary_kpi_module": "sql/api_modules/annual_summary_kpi_module.sql",
    "api.annual_summary_trend_module": "sql/api_modules/annual_summary_trend_module.sql",
    "api.annual_summary_platform_share_module": "sql/api_modules/annual_summary_platform_share_module.sql",
    "api.annual_summary_by_shop_module": "sql/api_modules/annual_summary_by_shop_module.sql",
}


def _visit(
    target: str,
    ordered: list[str],
    temporary: set[str],
    permanent: set[str],
) -> None:
    if target in permanent:
        return
    if target in temporary:
        raise ValueError(f"Cycle detected in refresh dependency graph at {target}")

    temporary.add(target)
    for dependency in PIPELINE_DEPENDENCIES.get(target, []):
        _visit(dependency, ordered, temporary, permanent)
    temporary.remove(target)
    permanent.add(target)
    if target not in ordered:
        ordered.append(target)


def topologically_sort_targets(targets: list[str]) -> list[str]:
    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()
    for target in targets:
        _visit(target, ordered, temporary, permanent)
    return ordered
