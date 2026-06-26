from __future__ import annotations

import re


PIPELINE_DEPENDENCIES: dict[str, list[str]] = {
    "semantic.alias_registry": [],
    "semantic.shop_identity_resolution_candidates": [],
    "semantic.fact_orders_monthly_atomic_mv": ["semantic.shop_identity_resolution_candidates"],
    "semantic.fact_analytics_monthly_atomic_mv": ["semantic.shop_identity_resolution_candidates"],
    "semantic.fact_orders_atomic": [],
    "semantic.fact_analytics_atomic": ["semantic.shop_identity_resolution_candidates"],
    "semantic.fact_orders_monthly_atomic": ["semantic.fact_orders_monthly_atomic_mv"],
    "semantic.fact_analytics_monthly_atomic": ["semantic.fact_analytics_monthly_atomic_mv"],
    "semantic.fact_products_atomic": ["semantic.alias_registry"],
    "semantic.fact_inventory_snapshot": [],
    "semantic.fact_services_atomic": [],
    "mart.shop_day_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.shop_hour_traffic_kpi": ["semantic.fact_analytics_atomic"],
    "mart.shop_week_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.shop_month_kpi": ["semantic.fact_orders_monthly_atomic", "semantic.fact_analytics_monthly_atomic"],
    "mart.platform_day_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.platform_week_kpi": ["semantic.fact_orders_atomic", "semantic.fact_analytics_atomic"],
    "mart.platform_month_kpi": ["mart.shop_month_kpi"],
    "mart.product_day_kpi": ["semantic.fact_products_atomic"],
    "mart.inventory_snapshot_history": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_snapshot_latest": ["mart.inventory_snapshot_history"],
    "mart.inventory_snapshot_change": ["mart.inventory_snapshot_history"],
    "mart.inventory_snapshot_company_daily": ["mart.inventory_snapshot_history"],
    "mart.inventory_age_history": ["mart.inventory_snapshot_company_daily"],
    "mart.inventory_age_current": ["mart.inventory_age_history"],
    "mart.inventory_current": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_backlog_base": ["mart.inventory_snapshot_latest", "mart.inventory_snapshot_change", "semantic.fact_orders_atomic"],
    "mart.hr_shop_monthly_profit": ["semantic.fact_orders_atomic"],
    "mart.b_cost_shop_month": ["semantic.fact_orders_atomic"],
    "api.business_overview_kpi_module": ["mart.platform_month_kpi"],
    "api.business_overview_comparison_platform_module": ["mart.platform_day_kpi", "mart.platform_week_kpi", "mart.platform_month_kpi"],
    "api.business_overview_comparison_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.business_overview_shop_racing_monthly_module": ["semantic.fact_orders_monthly_atomic"],
    "api.business_overview_shop_racing_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.business_overview_traffic_ranking_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.store_analysis_capability_module": ["mart.shop_month_kpi"],
    "api.store_analysis_traffic_summary_module": ["mart.shop_day_kpi", "mart.shop_week_kpi", "mart.shop_month_kpi"],
    "api.store_analysis_traffic_trend_module": ["mart.shop_hour_traffic_kpi", "mart.shop_day_kpi", "mart.shop_month_kpi"],
    "api.business_overview_inventory_backlog_module": ["mart.inventory_backlog_base"],
    "api.inventory_backlog_summary_module": ["mart.inventory_backlog_base"],
    "api.inventory_age_list_module": ["mart.inventory_age_current"],
    "api.inventory_age_summary_module": ["mart.inventory_age_current"],
    "api.business_overview_operational_metrics_module": ["mart.shop_month_kpi"],
    "api.b_cost_analysis_overview_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_shop_month_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_order_detail_module": ["semantic.fact_orders_atomic"],
    "api.clearance_ranking_module": ["mart.inventory_backlog_base", "api.inventory_backlog_summary_module"],
}

SQL_TARGET_PATHS: dict[str, str] = {
    "semantic.alias_registry": "sql/semantic/semantic_alias_registry.sql",
    "semantic.shop_identity_resolution_candidates": "sql/semantic/shop_identity_resolution_candidates.sql",
    "semantic.fact_orders_monthly_atomic_mv": "sql/semantic/orders_monthly_atomic_mv.sql",
    "semantic.fact_analytics_monthly_atomic_mv": "sql/semantic/analytics_monthly_atomic_mv.sql",
    "semantic.fact_orders_atomic": "sql/semantic/orders_atomic.sql",
    "semantic.fact_analytics_atomic": "sql/semantic/analytics_atomic.sql",
    "semantic.fact_orders_monthly_atomic": "sql/semantic/orders_monthly_atomic.sql",
    "semantic.fact_analytics_monthly_atomic": "sql/semantic/analytics_monthly_atomic.sql",
    "semantic.fact_products_atomic": "sql/semantic/products_atomic.sql",
    "semantic.fact_inventory_snapshot": "sql/semantic/inventory_snapshot.sql",
    "semantic.fact_services_atomic": "sql/semantic/services_atomic.sql",
    "mart.shop_day_kpi": "sql/mart/shop_day_kpi.sql",
    "mart.shop_hour_traffic_kpi": "sql/mart/shop_hour_traffic_kpi.sql",
    "mart.shop_week_kpi": "sql/mart/shop_week_kpi.sql",
    "mart.shop_month_kpi": "sql/mart/shop_month_kpi.sql",
    "mart.platform_day_kpi": "sql/mart/platform_day_kpi.sql",
    "mart.platform_week_kpi": "sql/mart/platform_week_kpi.sql",
    "mart.platform_month_kpi": "sql/mart/platform_month_kpi.sql",
    "mart.product_day_kpi": "sql/mart/product_day_kpi.sql",
    "mart.inventory_snapshot_history": "sql/mart/inventory_snapshot_history.sql",
    "mart.inventory_snapshot_latest": "sql/mart/inventory_snapshot_latest.sql",
    "mart.inventory_snapshot_change": "sql/mart/inventory_snapshot_change.sql",
    "mart.inventory_snapshot_company_daily": "sql/mart/inventory_snapshot_company_daily.sql",
    "mart.inventory_age_history": "sql/mart/inventory_age_history.sql",
    "mart.inventory_age_current": "sql/mart/inventory_age_current.sql",
    "mart.inventory_current": "sql/mart/inventory_current.sql",
    "mart.inventory_backlog_base": "sql/mart/inventory_backlog_base.sql",
    "mart.b_cost_shop_month": "sql/mart/b_cost_shop_month.sql",
    "api.business_overview_kpi_module": "sql/api_modules/business_overview_kpi_module.sql",
    "api.business_overview_comparison_platform_module": "sql/api_modules/business_overview_comparison_platform_module.sql",
    "api.business_overview_comparison_module": "sql/api_modules/business_overview_comparison_module.sql",
    "api.business_overview_shop_racing_monthly_module": "sql/api_modules/business_overview_shop_racing_monthly_module.sql",
    "api.business_overview_shop_racing_module": "sql/api_modules/business_overview_shop_racing_module.sql",
    "api.business_overview_traffic_ranking_module": "sql/api_modules/business_overview_traffic_ranking_module.sql",
    "api.store_analysis_capability_module": "sql/api_modules/store_analysis_capability_module.sql",
    "api.store_analysis_traffic_summary_module": "sql/api_modules/store_analysis_traffic_summary_module.sql",
    "api.store_analysis_traffic_trend_module": "sql/api_modules/store_analysis_traffic_trend_module.sql",
    "api.business_overview_inventory_backlog_module": "sql/api_modules/business_overview_inventory_backlog_module.sql",
    "api.inventory_backlog_summary_module": "sql/api_modules/inventory_backlog_summary_module.sql",
    "api.inventory_age_list_module": "sql/api_modules/inventory_age_list_module.sql",
    "api.inventory_age_summary_module": "sql/api_modules/inventory_age_summary_module.sql",
    "api.business_overview_operational_metrics_module": "sql/api_modules/business_overview_operational_metrics_module.sql",
    "api.b_cost_analysis_overview_module": "sql/api_modules/b_cost_analysis_overview_module.sql",
    "api.b_cost_analysis_shop_month_module": "sql/api_modules/b_cost_analysis_shop_month_module.sql",
    "api.b_cost_analysis_order_detail_module": "sql/api_modules/b_cost_analysis_order_detail_module.sql",
    "api.clearance_ranking_module": "sql/api_modules/clearance_ranking_module.sql",
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


def _reverse_dependencies() -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for target, dependencies in PIPELINE_DEPENDENCIES.items():
        for dependency in dependencies:
            reverse.setdefault(dependency, []).append(target)
    return reverse


def expand_downstream_targets(base_targets: list[str]) -> list[str]:
    """Return base targets and every registered downstream dependent in dependency order."""
    reverse = _reverse_dependencies()
    discovered: set[str] = set()
    stack = [target for target in base_targets if target in SQL_TARGET_PATHS]

    while stack:
        target = stack.pop()
        if target in discovered:
            continue
        discovered.add(target)
        stack.extend(reverse.get(target, []))

    return topologically_sort_targets([target for target in discovered if target in SQL_TARGET_PATHS])


def _normalize_table_name(source_table_name: str | None) -> str:
    raw_name = str(source_table_name or "").strip().lower()
    if "." in raw_name:
        raw_name = raw_name.rsplit(".", 1)[-1]
    return raw_name


def _infer_refresh_domain(
    *,
    source_table_name: str | None,
    data_domain: str | None,
) -> str | None:
    table_name = _normalize_table_name(source_table_name)
    normalized_domain = str(data_domain or "").strip().lower()
    if normalized_domain == "traffic":
        return "analytics"
    if normalized_domain in {"orders", "analytics", "products", "inventory", "services"}:
        return normalized_domain

    patterns = (
        ("orders", r"(^|_)orders(_|$)"),
        ("analytics", r"(^|_)(analytics|traffic)(_|$)"),
        ("products", r"(^|_)products(_|$)"),
        ("inventory", r"(^|_)inventory(_|$)"),
        ("services", r"(^|_)services(_|$)"),
    )
    for domain, pattern in patterns:
        if re.search(pattern, table_name):
            return domain
    return None


def _base_targets_for_refresh_domain(domain: str) -> list[str]:
    if domain == "orders":
        return [
            "semantic.fact_orders_atomic",
            "semantic.fact_orders_monthly_atomic_mv",
        ]
    if domain == "analytics":
        return [
            "semantic.fact_analytics_atomic",
            "semantic.fact_analytics_monthly_atomic_mv",
        ]
    if domain == "products":
        return ["semantic.fact_products_atomic"]
    if domain == "inventory":
        return ["semantic.fact_inventory_snapshot"]
    if domain == "services":
        return ["semantic.fact_services_atomic"]
    return []


def _extra_targets_for_refresh_domain(domain: str) -> list[str]:
    if domain in {"analytics", "orders"}:
        return [
            "api.business_overview_shop_racing_monthly_module",
        ]
    if domain == "inventory":
        return [
            "api.clearance_ranking_module",
        ]
    return []


def resolve_refresh_targets_for_source_table(
    *,
    source_table_name: str | None,
    data_domain: str | None = None,
    granularity: str | None = None,
) -> list[str]:
    """Resolve a synced B-class source table to the full affected refresh target graph."""
    del granularity
    domain = _infer_refresh_domain(
        source_table_name=source_table_name,
        data_domain=data_domain,
    )
    if domain is None:
        return []
    return expand_downstream_targets(
        [
            *_base_targets_for_refresh_domain(domain),
            *_extra_targets_for_refresh_domain(domain),
        ]
    )
