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
    _base_targets_for_refresh_domain,
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
    (
        # 库存语义层（2026-11-14）：正本每行都跑一次查表函数 ⇒ 读一次 197 ms。
        # 物化副本正文 = 正本正文 ⇒ 口径零变化。
        "semantic.fact_inventory_snapshot_mv",
        "semantic.fact_inventory_snapshot",
        "sql/semantic/inventory_snapshot_mv.sql",
    ),
)

#: 必须改读物化视图的消费方（否则还是 20 秒级）
CONSUMER_VIEW_ASSETS = (
    (
        "sql/mart/shop_day_kpi.sql",
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ),
    (
        "sql/mart/shop_week_kpi.sql",
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ),
    (
        "sql/mart/platform_day_kpi.sql",
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ),
    (
        "sql/mart/platform_week_kpi.sql",
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_analytics_atomic_mv",
    ),
    ("sql/mart/b_cost_shop_month.sql", "semantic.fact_orders_atomic_mv", None),
    (
        "sql/api_modules/b_cost_analysis_order_detail_module.sql",
        "semantic.fact_orders_atomic_mv",
        None,
    ),
)


def test_materialized_view_assets_are_registered():
    for mv_name, source_view, asset_path in MATERIALIZED_VIEW_ASSETS:
        assert mv_name in SQL_TARGET_PATHS, "{0} 未登记到 SQL_TARGET_PATHS".format(
            mv_name
        )
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
        assert (
            "DROP MATERIALIZED VIEW" not in executable
        ), "{0} 不允许 DROP MATERIALIZED VIEW —— 会连带删掉不可重建的下游".format(
            asset_path
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


def test_registry_does_not_register_objects_that_never_existed():
    """依赖表里不能登记「从来不存在、也没人能建出来」的对象。

    ``mart.hr_shop_monthly_profit`` 曾经登记在这里，但这个视图**从来没有建过**：

    - 仓库里没有对应的资产文件（``sql/mart/`` 下没有它）；
    - 生产库里也查不到它（2026-11-04 部署 v7.13.2 之前就查不到）；
    - 没有任何后端代码、SQL 资产或前端接口引用它。

    它属于「计划了但没实现」的悬空登记 —— 看起来像有一条薪资利润链路，其实没有。
    现在登记已删除，并把「登记的每个目标都必须能被资产文件重建」固化成断言，
    防止同类悬空登记再出现。
    """
    assert "mart.hr_shop_monthly_profit" not in PIPELINE_DEPENDENCIES
    for target in PIPELINE_DEPENDENCIES:
        assert (
            target in SQL_TARGET_PATHS
        ), "{0} 登记在依赖表里，却没有任何资产文件能重建它".format(target)


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
    assert plan.index("semantic.fact_orders_atomic_mv") < plan.index(
        "mart.shop_day_kpi"
    )
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


# ---------------------------------------------------------------------------
# 库存语义层物化副本（2026-11-14）
# ---------------------------------------------------------------------------


def test_inventory_domain_refresh_chain_lists_the_materialized_copy():
    """副本必须**显式**出现在库存域的刷新目标里。

    漏了 ⇒ 副本永远不被 REFRESH ⇒ 页面永远读着一份旧快照，
    而且**不报错**（products 域已经踩过同一个坑，注释写在 refresh_registry
    的同款分支里）。
    """
    targets = _base_targets_for_refresh_domain("inventory")
    assert "semantic.fact_inventory_snapshot" in targets
    assert "semantic.fact_inventory_snapshot_mv" in targets
    assert targets.index("semantic.fact_inventory_snapshot") < targets.index(
        "semantic.fact_inventory_snapshot_mv"
    )


def test_inventory_consumers_read_the_materialized_copy():
    """快照族 + 状态层必须读副本，且不得再直读正本。

    直读正本 = 每次查询都重算一遍标准化（生产实测 197 ms）
    ⇒ 这次改造等于没做。
    """
    for asset_path in (
        "sql/mart/inventory_snapshot_history.sql",
        "sql/mart/inventory_current.sql",
    ):
        sql_text = _read(asset_path)
        assert (
            "semantic.fact_inventory_snapshot_mv" in sql_text
        ), "{0} 必须读物化副本".format(asset_path)
        assert (
            "FROM semantic.fact_inventory_snapshot\n" not in sql_text
        ), "{0} 仍在直读普通视图".format(asset_path)

    # 状态层（库龄 / 距上次进货天数）的两条取数 SQL 同样读副本。
    service_text = _read(
        "backend/services/data_pipeline/inventory_state_refresh_service.py"
    )
    assert service_text.count("FROM semantic.fact_inventory_snapshot_mv") == 2
    assert "FROM semantic.fact_inventory_snapshot\n" not in service_text


def test_inventory_copy_guards_against_silent_shape_drift():
    """正本用 ``CREATE OR REPLACE VIEW`` ⇒ 加列时副本**不会**被连带删掉，
    而 ``REFRESH MATERIALIZED VIEW`` **不会新增列** ⇒ 副本会静默少一列。

    ⇒ 资产文件必须在刷新前比一次列集，不一致就报错停下（fail-closed），
    而不是带着旧形状继续刷。
    """
    sql_text = _read("sql/semantic/inventory_snapshot_mv.sql")
    assert "IS DISTINCT FROM" in sql_text
    assert "RAISE EXCEPTION" in sql_text
    # ⚠️ 列集必须用 ``pg_attribute`` 取：**不能用** ``information_schema.columns``。
    #    information_schema 只列 relkind ∈ {r,v,f,p}，**不含物化视图(relkind='m')**
    #    ⇒ 副本的列集永远取不到(NULL) ⇒ 守卫会把「一致」也判成「不一致」，
    #    副本从此刷不动。（2026-11-14 开发库实跑踩到）
    #    判据看的是 **FROM 后面跟什么**（注释里提到这个名字不算）。
    assert "FROM pg_attribute" in sql_text
    assert "FROM information_schema.columns" not in sql_text


def test_refresh_path_enforces_shape_guard_before_referencing():
    """数据刷新路径必须**真的**执行这道守卫。

    刷新计划对「已存在的物化视图」走的是**直接 REFRESH**（不执行资产文件，
    原因见 refresh_runner._refresh_materialized_view 的注释）⇒
    只把守卫写在资产文件里 = 守卫平时根本不生效 ⇒ 正本加列后副本静默少列，
    而且**全程不报错**。

    ⇒ 刷新路径在 REFRESH 之前必须自己比一次列集（源视图从资产文件解析，
    资产文件是 SSOT，不另立一份声明）。
    """
    runner_text = _read("backend/services/data_pipeline/refresh_runner.py")
    assert "_assert_materialized_view_shape" in runner_text
    assert "_materialized_view_source" in runner_text
    # 守卫必须**在** REFRESH 之前（顺序反了就等于没有）。
    guard_at = runner_text.index(
        "_assert_materialized_view_shape(db, target, source_view)"
    )
    refresh_at = runner_text.index("REFRESH MATERIALIZED VIEW {target}")
    assert guard_at < refresh_at, "形状守卫必须排在 REFRESH 之前"

    # 列集比较同样不能用 information_schema（不含物化视图）。
    assert "FROM pg_attribute" in runner_text
    assert "FROM information_schema.columns" not in runner_text
