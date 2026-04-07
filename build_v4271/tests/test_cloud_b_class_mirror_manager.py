from backend.services.cloud_b_class_mirror_manager import (
    build_canonical_columns,
    get_conflict_key_columns,
)


def test_build_canonical_columns_excludes_dynamic_fields():
    columns = build_canonical_columns()

    assert "platform_code" in columns
    assert "raw_data" in columns
    assert "header_columns" in columns
    assert "data_hash" in columns
    assert "dynamic_text_field" not in columns


def test_conflict_key_columns_differ_for_services():
    assert get_conflict_key_columns("orders") == (
        "platform_code",
        "shop_id",
        "data_domain",
        "granularity",
        "data_hash",
    )
    assert get_conflict_key_columns("services") == (
        "data_domain",
        "sub_domain",
        "granularity",
        "data_hash",
    )


def test_non_services_unique_index_sql_uses_plain_columns():
    manager = __import__(
        "backend.services.cloud_b_class_mirror_manager",
        fromlist=["CloudBClassMirrorManager"],
    ).CloudBClassMirrorManager(engine=None)

    sql = manager._build_conflict_index_sql("fact_shopee_orders_daily", "orders")

    assert "COALESCE" not in sql
    assert "(platform_code, shop_id, data_domain, granularity, data_hash)" in sql
