from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_semantic_alias_registry_sql_asset_defines_registry_and_resolver():
    sql_path = ROOT / "sql" / "semantic" / "semantic_alias_registry.sql"

    sql = sql_path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS semantic.semantic_field_aliases" in sql
    assert "CREATE OR REPLACE FUNCTION semantic.resolve_alias" in sql
    assert "商品 ID" in sql
    assert "商品名" in sql
    assert "发品状态" in sql


def test_products_atomic_uses_semantic_alias_resolver_for_key_fields():
    sql = (ROOT / "sql" / "semantic" / "products_atomic.sql").read_text(encoding="utf-8")

    assert "semantic.resolve_alias(raw_data, data_domain, 'product_id', platform_code, granularity)" in sql
    assert "semantic.resolve_alias(raw_data, data_domain, 'product_name', platform_code, granularity)" in sql
    assert "semantic.resolve_alias(raw_data, data_domain, 'item_status', platform_code, granularity)" in sql
    assert "semantic.resolve_alias(raw_data, data_domain, 'sales_amount', platform_code, granularity)" in sql
