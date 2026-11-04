"""原子层物化（2026-11-04）的结构契约。

背景
----
生产实测 ``mart.shop_day_kpi`` 单日聚合要 20.2 秒 → 业务概览与 B 成本页长期 504。
根因是 ``semantic.fact_orders_atomic`` 是普通视图：每行都跑一次店铺别名解析，
且 ``metric_date`` 过滤无法下推到去重窗口之下。

修法是把**整个原子视图**物化。本文件守住三条不变量：

1. **口径零变化** —— 物化视图的正文就是普通视图的正文（``SELECT * FROM <普通视图>``），
   物化只改「什么时候算」，不改「算什么」。
2. **不删任何下游** —— 物化视图的刷新走「存在则 REFRESH / 不存在则 CREATE」，
   不用 ``DROP ... CASCADE``：CASCADE 会连带删掉
   ``mart.hr_shop_monthly_profit`` / ``mart.inventory_backlog_base_mv``
   这类**不是 registry 可重建目标**的下游，以及不在 bootstrap 计划里的
   B 成本链。
3. **消费方确实读物化视图** —— 6 个慢接口的底层视图必须改读 MV。
"""

from pathlib import Path

from backend.services.data_pipeline.refresh_registry import (
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
    expand_downstream_targets,
    topologically_sort_targets,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


#: (物化视图, 它的数据来源普通视图, 资产文件)
MATERIALIZED_VIEW_ASSETS = (
    (
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_orders_atomic",
        "sql/semantic/orders_atomic_mv.sql",
    ),
    (
        "semantic.fact_analytics_atomic_mv",
        "semantic.fact_analytics_atomic",
        "sql/semantic/analytics_atomic_mv.sql",
    ),
)

#: 必须改读物化视图的消费方（否则还是 20 秒级）
CONSUMER_VIEW_ASSETS = (
    ("sql/mart/shop_day_kpi.sql", "semantic.fact_orders_atomic_mv", "semantic.fact_analytics_atomic_mv"),
    ("sql/mart/shop_week_kpi.sql", "semantic.fact_orders_atomic_mv", "semantic.fact_analytics_atomic_mv"),
    ("sql/mart/platform_day_kpi.sql", "semantic.fact_orders_atomic_mv", "semantic.fact_analytics_atomic_mv"),
    ("sql/mart/platform_week_kpi.sql", "semantic.fact_orders_atomic_mv", "semantic.fact_analytics_atomic_mv"),
    ("sql/mart/b_cost_shop_month.sql", "semantic.fact_orders_atomic_mv", None),
    (
        "sql/api_modules/b_cost_analysis_order_detail_module.sql",
        "semantic.fact_orders_atomic_mv",
        None,
    ),
)


def test_materialized_view_assets_are_registered():
    for mv_name, source_view, asset_path in MATERIALIZED_VIEW_ASSETS:
        assert mv_name in SQL_TARGET_PATHS, "{0} 未登记到 SQL_TARGET_PATHS".format(mv_name)
        assert SQL_TARGET_PATHS[mv_name] == asset_path
        assert mv_name in PIPELINE_DEPENDENCIES
        # 物化视图必须排在它所物化的普通视图**之后**
        assert PIPELINE_DEPENDENCIES[mv_name] == [source_view]


def test_materialized_view_body_is_the_plain_view_itself():
    """口径零变化的硬约束：正文必须是 ``SELECT * FROM <普通视图>``。

    如果哪天有人改成"照抄一份正文"或"换源重建粒度 MV"，
    这个断言会直接失败 —— 那正是会让 B 成本金额漂移的改法。
    """
    for mv_name, source_view, asset_path in MATERIALIZED_VIEW_ASSETS:
        sql_text = _read(asset_path)
        assert (
            "CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM {src}".format(
                mv=mv_name, src=source_view
            )
            in sql_text
        ), "{0} 的正文必须与普通视图同源".format(asset_path)


def _strip_sql_comments(sql_text: str) -> str:
    """去掉 ``--`` 行注释，避免把说明文字当成可执行语句。"""
    lines = []
    for line in sql_text.splitlines():
        cleaned = line.split("--", 1)[0]
        lines.append(cleaned)
    return "\n".join(lines)


def test_materialized_view_refresh_never_drops_downstream():
    """刷新必须是「存在则 REFRESH / 不存在则 CREATE」，不能 DROP CASCADE。

    CASCADE 会连带删掉不可重建的下游（B 成本链 / HR 利润视图），
    以及刷新期间出现「视图短暂消失」的窗口。
    """
    for mv_name, _source_view, asset_path in MATERIALIZED_VIEW_ASSETS:
        sql_text = _read(asset_path)
        executable = _strip_sql_comments(sql_text)
        assert "DROP MATERIALIZED VIEW" not in executable, (
            "{0} 不允许 DROP MATERIALIZED VIEW —— 会连带删掉不可重建的下游".format(
                asset_path
            )
        )
        assert "REFRESH MATERIALIZED VIEW {mv}".format(mv=mv_name) in executable
        assert "to_regclass('{mv}')".format(mv=mv_name) in executable


def test_materialized_views_have_supporting_indexes():
    for mv_name, _source_view, asset_path in MATERIALIZED_VIEW_ASSETS:
        sql_text = _read(asset_path)
        assert "CREATE INDEX IF NOT EXISTS" in sql_text
        assert "granularity, metric_date, platform_code, shop_id" in sql_text


def test_slow_consumers_read_the_materialized_views():
    for asset_path, orders_mv, analytics_mv in CONSUMER_VIEW_ASSETS:
        sql_text = _read(asset_path)
        assert orders_mv in sql_text, "{0} 必须读物化视图".format(asset_path)
        # 不得再直读普通视图（那正是 20 秒的来源）
        assert "FROM semantic.fact_orders_atomic\n" not in sql_text
        assert "FROM semantic.fact_analytics_atomic\n" not in sql_text
        if analytics_mv:
            assert analytics_mv in sql_text, "{0} 必须读物化视图".format(asset_path)


def test_hr_profit_view_keeps_reading_plain_view():
    """``mart.hr_shop_monthly_profit`` 不是 registry 可重建目标。

    它一旦改读物化视图，物化视图的 DROP CASCADE 会把它删掉且无人重建
    → 薪资链路断掉。所以它必须继续读普通视图。
    """
    assert PIPELINE_DEPENDENCIES["mart.hr_shop_monthly_profit"] == [
        "semantic.fact_orders_atomic"
    ]
    assert "mart.hr_shop_monthly_profit" not in SQL_TARGET_PATHS


def test_refresh_plan_orders_materialized_view_before_consumers():
    plan = topologically_sort_targets(
        [
            "semantic.fact_orders_atomic_mv",
            "mart.shop_day_kpi",
            "mart.b_cost_shop_month",
            "api.b_cost_analysis_order_detail_module",
        ]
    )
    assert plan.index("semantic.fact_orders_atomic") < plan.index(
        "semantic.fact_orders_atomic_mv"
    )
    assert plan.index("semantic.fact_orders_atomic_mv") < plan.index("mart.shop_day_kpi")
    assert plan.index("semantic.fact_orders_atomic_mv") < plan.index(
        "mart.b_cost_shop_month"
    )
    assert plan.index("semantic.fact_orders_atomic_mv") < plan.index(
        "api.b_cost_analysis_order_detail_module"
    )


def test_order_domain_refresh_covers_materialized_views_and_b_cost_chain():
    targets = expand_downstream_targets(
        [
            "semantic.fact_orders_atomic",
            "semantic.fact_orders_atomic_mv",
            "semantic.fact_orders_monthly_atomic_mv",
        ]
    )
    expected = {
        "semantic.fact_orders_atomic",
        "semantic.fact_orders_atomic_mv",
        "mart.shop_day_kpi",
        "mart.shop_week_kpi",
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "mart.b_cost_shop_month",
        "api.b_cost_analysis_order_detail_module",
        "api.b_cost_analysis_overview_module",
        "api.b_cost_analysis_shop_month_module",
    }
    assert expected.issubset(set(targets))
    assert targets.index("semantic.fact_orders_atomic_mv") < targets.index(
        "mart.b_cost_shop_month"
    )


def test_dashboard_bootstrap_refreshes_the_materialized_views():
    from backend.services.data_pipeline.dashboard_bootstrap import (
        DASHBOARD_MODULE_TARGETS,
    )

    refresh_targets = DASHBOARD_MODULE_TARGETS["business_overview"]["refresh_targets"]
    assert "semantic.fact_orders_atomic_mv" in refresh_targets
    assert "semantic.fact_analytics_atomic_mv" in refresh_targets
    assert "semantic.fact_orders_monthly_atomic_mv" in refresh_targets


def test_operational_metrics_module_declares_day_kpi_dependency():
    """经营指标模块的 SQL 资产里有一处 LEFT JOIN mart.shop_day_kpi。

    依赖表里必须写上，否则它可能在 mart.shop_day_kpi 之前重建，
    拿到旧的日粒度数据。
    """
    deps = PIPELINE_DEPENDENCIES["api.business_overview_operational_metrics_module"]
    assert "mart.shop_day_kpi" in deps
    sql_text = _read("sql/api_modules/business_overview_operational_metrics_module.sql")
    assert "mart.shop_day_kpi" in sql_text
