from backend.services.semantic_field_registry import infer_semantic_key, resolve_semantic_value


def test_semantic_registry_maps_order_number_aliases_to_order_id():
    assert infer_semantic_key("订单号") == "order_id"
    assert infer_semantic_key("订单编号") == "order_id"


def test_resolve_semantic_value_supports_order_number_aliases():
    row = {"订单编号": "A-001"}
    bindings = [
        {
            "raw_name": "订单编号",
            "display_name": "订单编号",
            "semantic_key": "order_id",
            "aliases": ["订单号", "订单编号"],
            "required": True,
            "hash_participates": True,
        }
    ]

    value, matched_key = resolve_semantic_value(row, "order_id", bindings)

    assert value == "A-001"
    assert matched_key == "订单编号"


def test_resolve_semantic_value_supports_normalized_currency_suffix_headers():
    row = {"平台SKU(MYR)": "SKU-001"}
    bindings = [
        {
            "raw_name": "平台SKU",
            "display_name": "平台SKU",
            "semantic_key": "platform_sku",
            "aliases": ["平台SKU", "platform_sku"],
            "required": False,
            "hash_participates": True,
        }
    ]

    value, matched_key = resolve_semantic_value(row, "platform_sku", bindings)

    assert value == "SKU-001"
    assert matched_key == "平台SKU(MYR)"
