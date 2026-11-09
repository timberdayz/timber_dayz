from __future__ import annotations

import re

from modules.core.data_domains import (
    DataDomain,
    data_domain_tokens_for,
    normalize_data_domain,
)


#: 刷新目标名与**真实数据库对象名**不一致的「逻辑目标」。
#:
#: 例：``semantic.alias_registry`` 的 SQL 建的是表 ``semantic.semantic_field_aliases``；
#: ``semantic.shop_identity_resolver`` 建的是**函数** ``semantic.resolve_shop_identity``。
#: 目标名只是刷新流程里的代号，存在性核对必须按真实对象名进行，
#: 否则会把活着的目标误报成 missing（⇒ 模块判 drift ⇒ 部署 bootstrap 被拦）。
#:
#: 维护约束：新增逻辑目标时必须登记在这里，由
#: ``test_data_pipeline_freshness_existence`` 守护。
LOGICAL_TARGET_OBJECTS: dict[str, str] = {
    "semantic.alias_registry": "semantic.semantic_field_aliases",
    # 共享的店铺身份解析函数：SQL 建的是**函数**，不是关系（pg_class 里没有）
    "semantic.shop_identity_resolver": "semantic.resolve_shop_identity",
    # 共享的仓名归一函数：同上，建的是**函数** semantic.resolve_warehouse_code
    "semantic.warehouse_resolver": "semantic.resolve_warehouse_code",
}


#: 语义层的**原子层视图**（普通视图，不是物化副本）。
#:
#: 为什么单独登记：它们的**定义**变更不会随数据刷新或 bootstrap 自动生效
#: （两者都跳过「已存在的普通视图」，见 ``refresh_runner.execute_sql_target``
#: 的 ``recreate_views=False``）⇒ 部署时必须**显式重建**，
#: 否则改了 ``sql/`` 资产也等于没改（曾经因此让商品/服务两条链路长期停在旧口径）。
#:
#: 部署脚本 ``scripts/deploy_remote_production.sh`` 的 ``DEPLOY_REBUILD_VIEW_TARGETS``
#: 默认值必须覆盖这一组，由 ``tests/test_verify_remote_deploy_contracts.py`` 守护。
PIPELINE_DEPENDENCIES: dict[str, list[str]] = {
    "semantic.alias_registry": [],
    # 身份解析候选集的**正本**仍是普通视图（从 core 表现算）；物化副本是它的
    # 快照，原子层两个普通视图改读物化副本。顺序不能反，否则建 MV 时正本还不存在。
    #
    # ⚠️ 采集方代号判定函数 ``semantic.is_collection_source_identifier``
    #    **内联在正本资产的开头**（谁执行正本, 函数先落地）⇒ 不需要单独登记
    #    刷新目标 —— 见 ``sql/semantic/shop_identity_resolution_candidates.sql``。
    "semantic.shop_identity_resolution_candidates": [],
    "semantic.shop_identity_resolution_candidates_v2_mv": [
        "semantic.shop_identity_resolution_candidates"
    ],
    # [*] 2026-11-08: orders 域取数改走 ``semantic.resolve_alias()``
    #   (别名表是取数的单一事实源) => 视图/物化视图建起来之前
    #   **别名资产必须先落地**(表 + 函数), 否则建视图报
    #   "function semantic.resolve_alias does not exist"。
    #   products 域早已登记了这个依赖, orders 域本轮补齐。
    "semantic.fact_orders_monthly_atomic_mv": [
        "semantic.shop_identity_resolution_candidates",
        "semantic.alias_registry",
    ],
    # [*] 2026-11-08: analytics(流量)域取数也改走 ``semantic.resolve_alias()``
    #   (别名表是取数的单一事实源) => 物化视图建起来之前**别名资产必须先落地**
    #   (表 + 函数), 否则报 "function semantic.resolve_alias does not exist"。
    #   orders 域早已登记, analytics 域本轮补齐(两条链同源, 口径必须一致)。
    "semantic.fact_analytics_monthly_atomic_mv": [
        "semantic.shop_identity_resolution_candidates",
        "semantic.alias_registry",
    ],
    # 原子层的两个**普通视图**改读物化副本（口径等价：副本正文 = 正本正文）
    # [*] 2026-11-08: orders 域取数改走 ``semantic.resolve_alias()``
    #   (别名表是取数的单一事实源) => 视图/物化视图建起来之前
    #   **别名资产必须先落地**(表 + 函数), 否则建视图报
    #   "function semantic.resolve_alias does not exist"。
    #   products 域早已登记了这个依赖, orders 域本轮补齐。
    "semantic.fact_orders_atomic": [
        "semantic.shop_identity_resolution_candidates_v2_mv",
        "semantic.alias_registry",
    ],
    # analytics(流量)域取数也改走 ``semantic.resolve_alias()``
    # => 别名资产（表 + 函数）必须先落地, 否则建视图报 "function does not exist"。
    "semantic.fact_analytics_atomic": [
        "semantic.shop_identity_resolution_candidates_v2_mv",
        "semantic.alias_registry",
    ],
    # 原子层的物化副本：正文与普通视图完全一致（SELECT *），只把「每行跑一次
    # 店铺别名解析」从请求路径搬到刷新路径。口径零变化。
    "semantic.fact_orders_atomic_mv": ["semantic.fact_orders_atomic"],
    "semantic.fact_analytics_atomic_mv": ["semantic.fact_analytics_atomic"],
    # 商品原子层的物化副本（2026-11-05）：商品日 KPI 读普通视图时每次请求都要
    # 重做「多表 UNION + 逐行 JSON 解析 + 逐行身份解析」（生产实测 14.1 秒），
    # 物化后请求侧毫秒级。正文 = 普通视图正文（SELECT *）⇒ 口径零变化。
    "semantic.fact_products_atomic_mv": ["semantic.fact_products_atomic"],
    "semantic.fact_orders_monthly_atomic": ["semantic.fact_orders_monthly_atomic_mv"],
    "semantic.fact_analytics_monthly_atomic": [
        "semantic.fact_analytics_monthly_atomic_mv"
    ],
    # 共享的「原始店铺标识 → 规范店铺键」解析函数。
    # 它读候选集的物化副本 ⇒ 必须在副本之后建（函数体在建函数时就校验依赖）。
    "semantic.shop_identity_resolver": [
        "semantic.shop_identity_resolution_candidates_v2_mv"
    ],
    # 下面三条链路以前**完全没做身份解析**，直接把采集文件里的原始 shop_id 透传出去
    # ⇒ 同一个店在不同链路里是三种键（平台店铺ID / 业务店铺ID / 原始店名 / 占位键）。
    # 现在统一走 resolve_shop_identity（口径与 orders_atomic 一致）。
    "semantic.fact_products_atomic": [
        "semantic.alias_registry",
        "semantic.shop_identity_resolver",
    ],
    # 库存原子层：仓码归一走 ``semantic.resolve_warehouse_code``（唯一归一实现）。
    # 该函数建在 ``core.dim_warehouse_name_aliases`` 对照表之上 ⇒ 函数资产必须
    # 先落地，否则建视图报 "function semantic.resolve_warehouse_code does not exist"。
    "semantic.fact_inventory_snapshot": [
        "semantic.shop_identity_resolver",
        "semantic.warehouse_resolver",
    ],
    "semantic.fact_services_atomic": ["semantic.shop_identity_resolver"],
    "semantic.shop_month_other_operating_cost": [],
    "mart.shop_day_kpi": [
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ],
    "mart.shop_week_kpi": [
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ],
    "mart.shop_month_kpi": [
        "semantic.fact_orders_monthly_atomic",
        "semantic.fact_analytics_monthly_atomic",
    ],
    "mart.platform_day_kpi": [
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ],
    "mart.platform_week_kpi": [
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ],
    "mart.platform_month_kpi": ["mart.shop_month_kpi"],
    "mart.product_day_kpi": ["semantic.fact_products_atomic_mv"],
    "mart.inventory_snapshot_history": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_snapshot_latest": ["mart.inventory_snapshot_history"],
    "mart.inventory_snapshot_change": ["mart.inventory_snapshot_history"],
    "mart.inventory_snapshot_company_daily": ["mart.inventory_snapshot_history"],
    "mart.inventory_age_history": ["mart.inventory_snapshot_company_daily"],
    "mart.inventory_age_current": ["mart.inventory_age_history"],
    "mart.inventory_current": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_state": ["semantic.fact_inventory_snapshot"],
    "mart.inventory_backlog_base": [
        "mart.inventory_snapshot_latest",
        "mart.inventory_state",
    ],
    "mart.spu_operating_current": ["mart.inventory_age_current"],
    "mart.b_cost_shop_month": ["semantic.fact_orders_atomic_mv"],
    "mart.shop_month_labor_cost": [],
    "api.business_overview_kpi_module": ["mart.platform_month_kpi"],
    "api.business_overview_comparison_platform_module": [
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "mart.platform_month_kpi",
    ],
    "api.business_overview_comparison_module": [
        "mart.shop_day_kpi",
        "mart.shop_week_kpi",
        "mart.shop_month_kpi",
    ],
    "api.business_overview_shop_racing_monthly_module": [
        "semantic.fact_orders_monthly_atomic"
    ],
    "api.business_overview_shop_racing_module": [
        "mart.shop_day_kpi",
        "mart.shop_week_kpi",
        "mart.shop_month_kpi",
    ],
    "api.business_overview_traffic_ranking_module": [
        "mart.shop_day_kpi",
        "mart.shop_week_kpi",
        "mart.shop_month_kpi",
    ],
    "api.business_overview_inventory_backlog_module": ["mart.inventory_backlog_base"],
    "api.inventory_backlog_summary_module": ["mart.inventory_backlog_base"],
    "api.inventory_age_list_module": ["mart.inventory_age_current"],
    "api.inventory_age_summary_module": ["mart.inventory_age_current"],
    "api.business_overview_operational_metrics_module": [
        "mart.shop_month_kpi",
        # ⚠️ 这个模块的 SQL 资产里有一处 LEFT JOIN mart.shop_day_kpi
        #    （today_sales / today_order_count 来自日粒度）。
        #    依赖表里必须写上，否则它可能在 mart.shop_day_kpi 之前重建，
        #    拿到旧的日粒度数据。
        "mart.shop_day_kpi",
        "semantic.shop_month_other_operating_cost",
        "mart.shop_month_labor_cost",
    ],
    "api.b_cost_analysis_overview_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_shop_month_module": ["mart.b_cost_shop_month"],
    "api.b_cost_analysis_order_detail_module": ["semantic.fact_orders_atomic_mv"],
    # SKU 级滞销清单：判据来自状态层（距上次进货天数），ERP 主数据补定价原料。
    # 2026-10-31：不再依赖 semantic.fact_orders_atomic —— 近30天动销改用妙手自带的
    # 窗口销量（状态层里已有），跨系统对账口径恒为 0，且那个视图每行跑一次店铺别名
    # 解析（10 秒级慢查询）。依赖列表跟着口径一起改，否则每次订单刷新都会白重建它。
    "api.sku_clearance_ranking_module": ["mart.inventory_state"],
}

SQL_TARGET_PATHS: dict[str, str] = {
    "semantic.alias_registry": "sql/semantic/semantic_alias_registry.sql",
    "semantic.shop_identity_resolution_candidates_v2_mv": (
        "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
    ),
    "semantic.shop_identity_resolution_candidates": "sql/semantic/shop_identity_resolution_candidates.sql",
    "semantic.shop_identity_resolver": "sql/semantic/shop_identity_resolver.sql",
    "semantic.warehouse_resolver": "sql/semantic/warehouse_resolver.sql",
    "semantic.fact_orders_monthly_atomic_mv": "sql/semantic/orders_monthly_atomic_mv.sql",
    "semantic.fact_analytics_monthly_atomic_mv": "sql/semantic/analytics_monthly_atomic_mv.sql",
    "semantic.fact_orders_atomic": "sql/semantic/orders_atomic.sql",
    "semantic.fact_analytics_atomic": "sql/semantic/analytics_atomic.sql",
    "semantic.fact_orders_atomic_mv": "sql/semantic/orders_atomic_mv.sql",
    "semantic.fact_analytics_atomic_mv": "sql/semantic/analytics_atomic_mv.sql",
    "semantic.fact_orders_monthly_atomic": "sql/semantic/orders_monthly_atomic.sql",
    "semantic.fact_analytics_monthly_atomic": "sql/semantic/analytics_monthly_atomic.sql",
    "semantic.fact_products_atomic": "sql/semantic/products_atomic.sql",
    "semantic.fact_products_atomic_mv": "sql/semantic/products_atomic_mv.sql",
    "semantic.fact_inventory_snapshot": "sql/semantic/inventory_snapshot.sql",
    "semantic.fact_services_atomic": "sql/semantic/services_atomic.sql",
    "semantic.shop_month_other_operating_cost": "sql/semantic/shop_month_other_operating_cost.sql",
    "mart.shop_day_kpi": "sql/mart/shop_day_kpi.sql",
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
    "mart.inventory_state": "sql/mart/inventory_state.sql",
    "mart.inventory_backlog_base": "sql/mart/inventory_backlog_base.sql",
    "mart.spu_operating_current": "sql/mart/spu_operating_current.sql",
    "mart.b_cost_shop_month": "sql/mart/b_cost_shop_month.sql",
    "mart.shop_month_labor_cost": "sql/mart/shop_month_labor_cost.sql",
    "api.business_overview_kpi_module": "sql/api_modules/business_overview_kpi_module.sql",
    "api.business_overview_comparison_platform_module": "sql/api_modules/business_overview_comparison_platform_module.sql",
    "api.business_overview_comparison_module": "sql/api_modules/business_overview_comparison_module.sql",
    "api.business_overview_shop_racing_monthly_module": "sql/api_modules/business_overview_shop_racing_monthly_module.sql",
    "api.business_overview_shop_racing_module": "sql/api_modules/business_overview_shop_racing_module.sql",
    "api.business_overview_traffic_ranking_module": "sql/api_modules/business_overview_traffic_ranking_module.sql",
    "api.business_overview_inventory_backlog_module": "sql/api_modules/business_overview_inventory_backlog_module.sql",
    "api.inventory_backlog_summary_module": "sql/api_modules/inventory_backlog_summary_module.sql",
    "api.inventory_age_list_module": "sql/api_modules/inventory_age_list_module.sql",
    "api.inventory_age_summary_module": "sql/api_modules/inventory_age_summary_module.sql",
    "api.business_overview_operational_metrics_module": "sql/api_modules/business_overview_operational_metrics_module.sql",
    "api.b_cost_analysis_overview_module": "sql/api_modules/b_cost_analysis_overview_module.sql",
    "api.b_cost_analysis_shop_month_module": "sql/api_modules/b_cost_analysis_shop_month_module.sql",
    "api.b_cost_analysis_order_detail_module": "sql/api_modules/b_cost_analysis_order_detail_module.sql",
    "api.sku_clearance_ranking_module": "sql/api_modules/sku_clearance_ranking_module.sql",
}

#: 语义层的**原子层视图**（普通视图，不是物化副本）。
#:
#: 为什么单独登记：它们的**定义**变更不会随数据刷新或 bootstrap 自动生效
#: （两者都跳过「已存在的普通视图」，见 ``refresh_runner.execute_sql_target``
#: 的 ``recreate_views=False``）⇒ 部署时必须**显式重建**，
#: 否则改了 ``sql/`` 资产也等于没改（曾经因此让商品/服务两条链路长期停在旧口径）。
#:
#: 部署脚本 ``scripts/deploy_remote_production.sh`` 的 ``DEPLOY_REBUILD_VIEW_TARGETS``
#: 默认值必须覆盖这一组，由 ``tests/test_verify_remote_deploy_contracts.py`` 守护。
SEMANTIC_ATOMIC_VIEW_TARGETS: list[str] = sorted(
    target
    for target in SQL_TARGET_PATHS
    if target.startswith("semantic.fact_") and not target.endswith("_mv")
)

#: 建对象**前置**：目标资产在执行前必须先就位的对象。
#:
#: 与 ``PIPELINE_DEPENDENCIES`` 的区别：
#: - ``PIPELINE_DEPENDENCIES`` 是「刷新顺序」（谁先刷）；
#: - 这里是「**建对象**的前置」—— 目标资产的正文**引用**了这些对象，
#:   它们不存在时建视图会直接报 ``relation does not exist``。
#:
#: 例：``semantic.fact_orders_atomic`` 的正文引用候选集物化副本
#: ``semantic.shop_identity_resolution_candidates_v2_mv``（把「每行订单事实
#: 重算 136 行候选集」的 N+1 干掉），副本不存在 ⇒ 建视图失败。
#:
#: 前置对象已存在时会被跳过/刷新，代价可忽略（副本只有 136 行，刷新毫秒级）。
ASSET_PREREQUISITES: dict[str, list[str]] = {
    "semantic.fact_orders_atomic": [
        "semantic.shop_identity_resolution_candidates_v2_mv",
        "semantic.alias_registry",
    ],
    # [*] 2026-11-08: orders 域取数改走 ``semantic.resolve_alias()``
    #   (别名表是取数的单一事实源) => 视图/物化视图建起来之前
    #   **别名资产必须先落地**(表 + 函数), 否则建视图报
    #   "function semantic.resolve_alias does not exist"。
    #   products 域早已登记了这个依赖, orders 域本轮补齐。
    "semantic.fact_orders_monthly_atomic_mv": [
        "semantic.alias_registry",
    ],
    "semantic.fact_analytics_atomic": [
        "semantic.shop_identity_resolution_candidates_v2_mv",
        "semantic.alias_registry",
    ],
    # analytics 域的物化视图/普通视图正文都调 ``semantic.resolve_alias()``
    # => 别名资产（表 + 函数）是**建对象前置**, 不存在时直接建不出来。
    "semantic.fact_analytics_atomic_mv": ["semantic.alias_registry"],
    "semantic.fact_analytics_monthly_atomic_mv": ["semantic.alias_registry"],
    "semantic.fact_analytics_monthly_atomic": ["semantic.alias_registry"],
    # 库存原子层的正文调用三个**共享函数**：
    #   ``semantic.resolve_shop_identity``          （店铺身份解析，LEFT JOIN LATERAL）
    #   ``semantic.resolve_warehouse_code``         （仓名 → 规范仓码）
    #   ``semantic.is_collection_source_identifier`` （采集方代号判定，
    #     **内联在候选池正本资产的开头** ⇒ 候选池正本是它的建对象前置)
    # 函数不存在时视图**直接建不出来** ⇒ 三个函数都是建对象前置。
    "semantic.fact_inventory_snapshot": [
        "semantic.shop_identity_resolver",
        "semantic.warehouse_resolver",
        "semantic.shop_identity_resolution_candidates",
    ],
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

    return topologically_sort_targets(
        [target for target in discovered if target in SQL_TARGET_PATHS]
    )


def _normalize_table_name(source_table_name: str | None) -> str:
    raw_name = str(source_table_name or "").strip().lower()
    if "." in raw_name:
        raw_name = raw_name.rsplit(".", 1)[-1]
    return raw_name


#: 有刷新目标图的业务域(与 _base_targets_for_refresh_domain 的分支保持一致)
_REFRESHABLE_DOMAINS = frozenset(
    {"orders", "analytics", "products", "inventory", "services"}
)


def _infer_refresh_domain(
    *,
    source_table_name: str | None,
    data_domain: str | None,
) -> str | None:
    table_name = _normalize_table_name(source_table_name)
    # [D8] 归一数据域(traffic -> analytics)统一走 SSOT,不再在这里写死别名
    normalized_domain = normalize_data_domain(data_domain)
    if normalized_domain in _REFRESHABLE_DOMAINS:
        return normalized_domain

    # [D8] analytics 的表名正则同时认新表名与历史 traffic 表名
    analytics_tokens = data_domain_tokens_for(DataDomain.ANALYTICS.value)
    patterns = (
        ("orders", r"(^|_)orders(_|$)"),
        ("analytics", r"(^|_)(%s)(_|$)" % "|".join(analytics_tokens)),
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
            "semantic.fact_orders_atomic_mv",
            "semantic.fact_orders_monthly_atomic_mv",
        ]
    if domain == "analytics":
        return [
            "semantic.fact_analytics_atomic",
            "semantic.fact_analytics_atomic_mv",
            "semantic.fact_analytics_monthly_atomic_mv",
        ]
    if domain == "products":
        # 物化副本必须显式列出来（2026-11-11）：
        # 商品域的刷新链是「普通视图 → 物化副本 → 商品日 KPI」，
        # 副本不在链上 ⇒ 商品经营分析页会永远读着一份建库时的旧快照。
        return [
            "semantic.fact_products_atomic",
            "semantic.fact_products_atomic_mv",
        ]
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
        # ⚠️ 这三个 api 视图都依赖 `mart.inventory_backlog_base`，
        #    而基表删列 → 必须 DROP 重建 → DROP 会连带删掉这三个下游。
        #    refresh pipeline 只重建列出来的目标 → 少列一个就少重建一个，
        #    表现为「采集跑完，业务概览的积压视图突然 missing」。
        #    → 三个全带。
        return [
            "api.business_overview_inventory_backlog_module",
            "api.inventory_backlog_summary_module",
            "api.sku_clearance_ranking_module",
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
