import pytest


@pytest.mark.asyncio
async def test_builtin_alias_resolves_new_tiktok_product_headers():
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService

    service = SemanticAliasRegistryService()

    assert service.resolve_alias_from_row(
        {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
        data_domain="products",
        standard_field="product_id",
        platform_code="tiktok",
        granularity="daily",
    ) == "172939"
    assert service.resolve_alias_from_row(
        {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
        data_domain="products",
        standard_field="product_name",
        platform_code="tiktok",
        granularity="daily",
    ) == "Summer Shirt"
    assert service.resolve_alias_from_row(
        {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
        data_domain="products",
        standard_field="item_status",
        platform_code="tiktok",
        granularity="daily",
    ) == "active"


def test_template_confirmed_bindings_create_aliases_without_duplicates():
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService

    service = SemanticAliasRegistryService()
    header_bindings = [
        {
            "source_header": "商品 ID",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
        },
        {
            "source_header": "商品名",
            "semantic_key": None,
            "semantic_review_status": "confirmed_non_semantic",
        },
    ]

    first = service.collect_aliases_from_template_bindings(
        data_domain="products",
        platform_code="tiktok",
        granularity="daily",
        header_bindings=header_bindings,
    )
    second = service.collect_aliases_from_template_bindings(
        data_domain="products",
        platform_code="tiktok",
        granularity="daily",
        header_bindings=header_bindings,
    )

    assert first == second
    assert first == [
        {
            "data_domain": "products",
            "standard_field": "product_id",
            "raw_alias": "商品 ID",
            "platform_code": "tiktok",
            "granularity": "daily",
            "source": "template_confirmed",
        }
    ]
