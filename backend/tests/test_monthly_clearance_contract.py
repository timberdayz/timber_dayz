from pathlib import Path


def test_clearance_ranking_sql_is_monthly_shop_aggregation():
    sql = Path("sql/api_modules/clearance_ranking_module.sql").read_text(encoding="utf-8")
    normalized = sql.lower()
    assert "semantic.fact_orders_atomic" in normalized
    assert "ranking_month" in normalized
    assert "shop_name" in normalized
    assert "clearance_amount" in normalized
    assert "clearance_quantity" in normalized
    assert "group by" in normalized
