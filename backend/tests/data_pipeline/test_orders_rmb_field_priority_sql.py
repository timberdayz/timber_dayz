from pathlib import Path


def _assert_prefer(sql_text: str, marker: str, preferred: str, fallback: str):
    before = sql_text.split(marker, 1)[0]
    block = before.rsplit("COALESCE(", 1)[-1]
    assert preferred in block
    assert fallback in block
    assert block.index(preferred) < block.index(fallback)


def test_orders_atomic_sql_prefers_rmb_profit_and_amount_fields():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_prefer(sql_text, "AS profit_raw", "raw_data->>'利润(RMB)'", "raw_data->>'利润'")
    _assert_prefer(
        sql_text,
        "AS platform_commission_raw",
        "raw_data->>'平台佣金(RMB)'",
        "raw_data->>'平台佣金'",
    )


def test_orders_model_sql_prefers_rmb_profit_and_amount_fields():
    sql_text = Path("sql/metabase_models/orders_model.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_prefer(sql_text, "AS profit_raw", "raw_data->>'profit_rmb'", "raw_data->>'profit'")
    _assert_prefer(
        sql_text,
        "AS estimated_settlement_amount_raw",
        "raw_data->>'estimated_settlement_rmb'",
        "raw_data->>'estimated_settlement'",
    )
    _assert_prefer(
        sql_text,
        "AS platform_commission_raw",
        "raw_data->>'platform_commission_rmb'",
        "raw_data->>'platform_commission'",
    )
