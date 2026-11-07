import pytest


@pytest.mark.asyncio
async def test_builtin_alias_resolves_new_tiktok_product_headers():
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService

    service = SemanticAliasRegistryService()

    assert (
        service.resolve_alias_from_row(
            {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
            data_domain="products",
            standard_field="product_id",
            platform_code="tiktok",
            granularity="daily",
        )
        == "172939"
    )
    assert (
        service.resolve_alias_from_row(
            {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
            data_domain="products",
            standard_field="product_name",
            platform_code="tiktok",
            granularity="daily",
        )
        == "Summer Shirt"
    )
    assert (
        service.resolve_alias_from_row(
            {"商品 ID": "172939", "商品名": "Summer Shirt", "发品状态": "active"},
            data_domain="products",
            standard_field="item_status",
            platform_code="tiktok",
            granularity="daily",
        )
        == "active"
    )


def test_template_confirmed_bindings_create_aliases_without_duplicates():
    """用户确认过的对齐沉淀成**全局**别名(D-3 决策: 一处对齐, 处处生效)。

    ⇒ 沉淀出来的别名**不限**数据域 / 平台 / 粒度:
    只放开数据域、还留着平台与粒度的话, 同一个列名在另一个平台再对齐一次
    会变成「另一条记录」⇒ 冲突检测漏掉, 「一处生效」也名不副实。
    """
    from backend.services.semantic_alias_registry import (
        GLOBAL_ALIAS_DOMAIN,
        SemanticAliasRegistryService,
    )

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
            "data_domain": GLOBAL_ALIAS_DOMAIN,
            "standard_field": "product_id",
            "raw_alias": "商品 ID",
            "platform_code": None,
            "granularity": None,
            "source": "template_confirmed",
        }
    ]


def test_template_confirmed_bindings_keep_domain_scope_when_asked():
    """显式 ``global_scope=False`` 时才按域沉淀(域 / 平台 / 粒度都带着)。"""
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService

    service = SemanticAliasRegistryService()

    aliases = service.collect_aliases_from_template_bindings(
        data_domain="products",
        platform_code="tiktok",
        granularity="monthly",
        header_bindings=[
            {
                "raw_name": "Product ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        global_scope=False,
    )

    assert aliases == [
        {
            "data_domain": "products",
            "standard_field": "product_id",
            "raw_alias": "Product ID",
            "platform_code": "tiktok",
            "granularity": "monthly",
            "source": "template_confirmed",
        }
    ]


def test_template_confirmed_bindings_collect_raw_name_aliases():
    from backend.services.semantic_alias_registry import (
        GLOBAL_ALIAS_DOMAIN,
        SemanticAliasRegistryService,
    )

    service = SemanticAliasRegistryService()

    aliases = service.collect_aliases_from_template_bindings(
        data_domain="products",
        platform_code="tiktok",
        granularity="monthly",
        header_bindings=[
            {
                "raw_name": "Product ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "Item Status",
                "semantic_key": "item_status",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "GMV",
                "semantic_key": "gmv",
                "semantic_review_status": "pending",
            },
        ],
    )

    # 只有 **confirmed_semantic** 的绑定才会沉淀(``pending`` 不算数)。
    assert aliases == [
        {
            "data_domain": GLOBAL_ALIAS_DOMAIN,
            "standard_field": "product_id",
            "raw_alias": "Product ID",
            "platform_code": None,
            "granularity": None,
            "source": "template_confirmed",
        },
        {
            "data_domain": GLOBAL_ALIAS_DOMAIN,
            "standard_field": "item_status",
            "raw_alias": "Item Status",
            "platform_code": None,
            "granularity": None,
            "source": "template_confirmed",
        },
    ]
