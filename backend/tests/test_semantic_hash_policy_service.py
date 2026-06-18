from backend.services.semantic_hash_policy_service import SemanticHashPolicyService


def test_products_item_status_is_legacy_compatible_weak_hash_option():
    service = SemanticHashPolicyService()

    option = service.evaluate_option(
        data_domain="products",
        granularity="daily",
        sub_domain=None,
        semantic_key="item_status",
    )

    assert option.semantic_key == "item_status"
    assert option.eligible is True
    assert option.recommended is False
    assert option.weak_identity is True
    assert option.legacy_compatible is True
    assert option.blocked_reason is None
    assert option.warning


def test_metrics_remain_blocked_hash_options():
    service = SemanticHashPolicyService()

    options = [
        service.evaluate_option(
            data_domain="products",
            granularity="daily",
            sub_domain=None,
            semantic_key=semantic_key,
        )
        for semantic_key in ["gmv", "sales_amount", "page_views"]
    ]

    assert [option.eligible for option in options] == [False, False, False]
    assert all(option.blocked_reason for option in options)


def test_build_options_uses_confirmed_semantic_bindings_only():
    service = SemanticHashPolicyService()

    options = service.build_options(
        data_domain="products",
        granularity="daily",
        sub_domain=None,
        header_bindings=[
            {
                "raw_name": "Product ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "Listing Status",
                "semantic_key": "item_status",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "GMV",
                "semantic_key": "gmv",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "Unknown Field",
                "semantic_key": None,
                "semantic_review_status": "pending",
            },
        ],
    )

    by_key = {option["semantic_key"]: option for option in options}
    assert by_key["product_id"]["eligible"] is True
    assert by_key["product_id"]["recommended"] is True
    assert by_key["item_status"]["eligible"] is True
    assert by_key["item_status"]["weak_identity"] is True
    assert by_key["item_status"]["legacy_compatible"] is True
    assert by_key["gmv"]["eligible"] is False
    assert "Unknown Field" not in {option.get("raw_name") for option in options}
