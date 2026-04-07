from pathlib import Path


def test_field_alias_rules_sql_exists_and_defines_core_table():
    sql_path = Path("sql/ops/create_field_alias_rules.sql")
    assert sql_path.exists()

    sql_text = sql_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS core.field_alias_rules" in sql_text
    assert "standard_field_name" in sql_text
    assert "source_field_name" in sql_text


def test_group_rules_by_standard_field_orders_aliases():
    from backend.services.field_alias_rule_service import group_rules_by_standard_field

    grouped = group_rules_by_standard_field(
        [
            {
                "platform_code": "tiktok",
                "data_domain": "orders",
                "standard_field_name": "sales_amount",
                "source_field_name": "销售金额",
                "priority": 100,
                "active": True,
            },
            {
                "platform_code": "tiktok",
                "data_domain": "orders",
                "standard_field_name": "sales_amount",
                "source_field_name": "GMV",
                "priority": 50,
                "active": True,
            },
            {
                "platform_code": "tiktok",
                "data_domain": "orders",
                "standard_field_name": "order_id",
                "source_field_name": "订单ID",
                "priority": 90,
                "active": True,
            },
        ]
    )

    assert list(grouped.keys()) == ["sales_amount", "order_id"]
    assert [row["source_field_name"] for row in grouped["sales_amount"]] == ["销售金额", "GMV"]


def test_filter_rules_by_scope():
    from backend.services.field_alias_rule_service import filter_rules_by_scope

    filtered = filter_rules_by_scope(
        rules=[
            {
                "platform_code": "tiktok",
                "data_domain": "orders",
                "sub_domain": None,
                "standard_field_name": "sales_amount",
                "source_field_name": "销售金额",
                "priority": 100,
                "active": True,
            },
            {
                "platform_code": "shopee",
                "data_domain": "orders",
                "sub_domain": None,
                "standard_field_name": "sales_amount",
                "source_field_name": "销售额",
                "priority": 100,
                "active": True,
            },
            {
                "platform_code": "tiktok",
                "data_domain": "analytics",
                "sub_domain": None,
                "standard_field_name": "gmv",
                "source_field_name": "GMV",
                "priority": 100,
                "active": True,
            },
        ],
        platform_code="tiktok",
        data_domain="orders",
        sub_domain=None,
    )

    assert len(filtered) == 1
    assert filtered[0]["source_field_name"] == "销售金额"
