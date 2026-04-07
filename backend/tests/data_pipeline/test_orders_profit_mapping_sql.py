from pathlib import Path


def test_orders_atomic_sql_does_not_map_net_profit_into_profit_raw():
    sql_text = Path("sql/semantic/orders_atomic.sql").read_text(
        encoding="utf-8", errors="replace"
    )
    before = sql_text.split("AS profit_raw", 1)[0]
    block = before.rsplit("COALESCE(", 1)[-1]
    assert "net_profit" not in block
    assert "净利" not in block


def test_orders_model_sql_does_not_map_net_profit_into_profit_raw():
    sql_text = Path("sql/metabase_models/orders_model.sql").read_text(
        encoding="utf-8", errors="replace"
    )
    before = sql_text.split("AS profit_raw", 1)[0]
    block = before.rsplit("COALESCE(", 1)[-1]
    assert "net_profit" not in block
    assert "净利" not in block
