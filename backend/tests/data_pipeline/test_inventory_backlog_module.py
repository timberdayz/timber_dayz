from pathlib import Path


def _strip_sql_comments(sql_text: str) -> str:
    """去掉 SQL 注释行，只留真正的语句。"""
    return "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )


def _assert_sql_asset(path_str: str, expected_prefix: str, required_terms: tuple[str, ...]) -> None:
    sql_path = Path(path_str)
    assert sql_path.exists()
    sql_text = sql_path.read_text(encoding="utf-8")
    assert expected_prefix in sql_text
    for term in required_terms:
        assert term in sql_text


def test_product_day_kpi_sql_asset():
    _assert_sql_asset(
        "sql/mart/product_day_kpi.sql",
        "CREATE OR REPLACE VIEW mart.product_day_kpi AS",
        (
            "semantic.fact_products_atomic",
            "metric_date",
            "platform_code",
            "shop_id",
            "platform_sku",
            "sales_amount",
            "order_count",
        ),
    )


def test_inventory_current_sql_asset():
    _assert_sql_asset(
        "sql/mart/inventory_current.sql",
        "CREATE OR REPLACE VIEW mart.inventory_current AS",
        (
            "semantic.fact_inventory_snapshot",
            "ROW_NUMBER() OVER",
            "available_stock",
            "inventory_value",
            "snapshot_date",
        ),
    )


def test_inventory_backlog_base_sql_asset():
    """滞销判据换成「距上次进货时长」；9999 哨兵与两个假指标必须从源头消失。"""
    _assert_sql_asset(
        "sql/mart/inventory_backlog_base.sql",
        "CREATE OR REPLACE VIEW mart.inventory_backlog_base AS",
        (
            "mart.inventory_snapshot_latest",
            "mart.inventory_state",
            "stock_added_at",
            "row_seen_at",
            "row_written_at",
            "days_since_restock",
            "checklist_sales_30d",
            "checklist_sales_90d",
            "available_stock",
            "inventory_value",
        ),
    )
    sql_text = Path("sql/mart/inventory_backlog_base.sql").read_text(encoding="utf-8")
    assert "joined_backlog AS" in sql_text
    # 旧的假指标与 9999 哨兵必须彻底消失（只看代码，注释里提到它们是正常的说明文字）
    code_text = _strip_sql_comments(sql_text)
    for removed in (
        "estimated_turnover_days",
        "daily_avg_sales",
        "risk_level",
        "clearance_priority_score",
        "stagnant_snapshot_count",
        "estimated_stagnant_days",
        "9999",
    ):
        assert removed not in code_text


def test_inventory_backlog_base_sql_does_not_divide_in_sql():
    """DOS 的除法必须在 Python（唯一实现），SQL 只放原子事实。"""
    sql_text = Path("sql/mart/inventory_backlog_base.sql").read_text(encoding="utf-8")
    assert "checklist_sales_90d::numeric /" not in sql_text
    assert "/" not in sql_text.split("days_since_restock")[0].split("AS days_since_restock")[-1][-60:]


def test_inventory_backlog_base_sql_drops_order_domain_sales_cte():
    """订单域对 miaoshou 全空，销量必须来自库存清单自带的列。"""
    sql_text = Path("sql/mart/inventory_backlog_base.sql").read_text(encoding="utf-8")
    assert "semantic.fact_orders_atomic" not in sql_text


def test_inventory_snapshot_latest_sql_uses_company_scope_not_shop_scope():
    sql_text = Path("sql/mart/inventory_snapshot_latest.sql").read_text(encoding="utf-8")
    assert "PARTITION BY platform_code" in sql_text
    assert "COALESCE(shop_id, '')" not in sql_text
    # 增量模式下同一天可能落多批 → 必须先按 (snapshot_date, SKU×仓) 取最新一行，
    # 不能直接 SUM（会把同一行重复累加，库存凭空翻倍）。
    # 行为由 test_inventory_snapshot_views_behavior.py 在真实 PostgreSQL 上守住。
    assert "ROW_NUMBER() OVER" in sql_text
    assert "day_rn = 1" in sql_text


def test_inventory_snapshot_change_sql_uses_company_scope_not_shop_scope():
    sql_text = Path("sql/mart/inventory_snapshot_change.sql").read_text(encoding="utf-8")
    assert "PARTITION BY platform_code" in sql_text
    assert "COALESCE(shop_id, '')" not in sql_text
    assert "ROW_NUMBER() OVER" in sql_text
    assert "day_rn = 1" in sql_text


def test_inventory_backlog_base_sql_is_company_scope_not_shop_scope():
    sql_text = Path("sql/mart/inventory_backlog_base.sql").read_text(encoding="utf-8")
    assert "NULL::text AS shop_id" in sql_text
    assert "COALESCE(i.shop_id, '') = COALESCE(s.shop_id, '')" not in sql_text


def test_inventory_backlog_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/business_overview_inventory_backlog_module.sql",
        "CREATE OR REPLACE VIEW api.business_overview_inventory_backlog_module AS",
        (
            "mart.inventory_backlog_base",
            "stock_added_at",
            "row_seen_at",
            "days_since_restock",
            "checklist_sales_30d",
            "checklist_sales_90d",
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )
    sql_text = Path("sql/api_modules/business_overview_inventory_backlog_module.sql").read_text(
        encoding="utf-8"
    )
    # 旧字段（estimated_turnover_days / risk_level / clearance_priority_score 等）
    # 必须整条链都消失：源头、api 视图都不许再出现
    for removed in (
        "estimated_turnover_days",
        "daily_avg_sales",
        "risk_level",
        "clearance_priority_score",
        "stagnant_snapshot_count",
        "9999",
    ):
        assert removed not in _strip_sql_comments(sql_text)


def test_inventory_backlog_summary_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/inventory_backlog_summary_module.sql",
        "CREATE OR REPLACE VIEW api.inventory_backlog_summary_module AS",
        (
            "mart.inventory_backlog_base",
            "deep_stagnant_value",
            "mid_stagnant_value",
            "deep_stagnant_row_count",
            "mid_stagnant_row_count",
            "unknown_restock_row_count",
        ),
    )


def test_clearance_ranking_module_sql_asset():
    _assert_sql_asset(
        "sql/api_modules/clearance_ranking_module.sql",
        "CREATE OR REPLACE VIEW api.clearance_ranking_module AS",
        (
            "mart.inventory_backlog_base",
            "estimated_turnover_days",
            "daily_avg_sales",
            "stagnant_snapshot_count",
            "estimated_stagnant_days",
            "risk_level",
            "clearance_priority_score",
            "inventory_value",
            "platform_code",
            "shop_id",
            "platform_sku",
        ),
    )
