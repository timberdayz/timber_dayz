from pathlib import Path


def test_shop_identity_resolution_sql_asset():
    sql_path = Path("sql/semantic/shop_identity_resolution_candidates.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS semantic" in sql_text
    assert "CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS" in sql_text
    assert "core.shop_accounts" in sql_text
    assert "core.shop_account_aliases" in sql_text
    assert "platform_shop_id" in sql_text
    assert "shop_account_id" in sql_text
    assert "resolution_method" in sql_text
    assert "resolved_shop_id" in sql_text
