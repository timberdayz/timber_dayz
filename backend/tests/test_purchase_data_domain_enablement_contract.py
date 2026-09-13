"""
采购数据域启用契约测试（feat/miaoshou-purchase-frontend-enable 配套）

约束：保持加性扩展，不破坏 finance / orders / products / analytics / services / inventory 现有契约。
"""

from backend.services.collection_contracts import (
    DEFAULT_CONFIG_DATA_DOMAINS,
    get_default_shop_capabilities,
    get_recommended_config_domains,
    get_supported_config_data_domains,
    resolve_shop_capabilities,
)


def test_default_config_data_domains_includes_purchase():
    assert "purchase" in DEFAULT_CONFIG_DATA_DOMAINS


def test_default_config_data_domains_preserves_existing_six():
    expected = {"orders", "products", "analytics", "finance", "services", "inventory", "purchase"}
    assert set(DEFAULT_CONFIG_DATA_DOMAINS) == expected


def test_get_default_shop_capabilities_includes_purchase_true():
    caps = get_default_shop_capabilities(shop_type="regional")
    assert caps.get("purchase") is True


def test_get_default_shop_capabilities_preserves_existing_six():
    caps = get_default_shop_capabilities(shop_type="regional")
    for domain in ("orders", "products", "analytics", "finance", "services", "inventory"):
        assert caps.get(domain) is True, f"existing domain {domain} must remain True"


def test_get_supported_config_data_domains_returns_purchase():
    domains = get_supported_config_data_domains(platform="miaoshou")
    assert "purchase" in domains


def test_resolve_shop_capabilities_when_missing_purchase_in_db_row_returns_default_true():
    """店铺 capability 表只存了 orders=true；purchase 未写入时，应默认 True"""
    db_caps = {"orders": True}
    resolved = resolve_shop_capabilities(db_caps, shop_type="regional")
    assert resolved.get("purchase") is True
    assert resolved.get("orders") is True


def test_get_recommended_config_domains_includes_purchase():
    domains = get_recommended_config_domains(
        capabilities={"orders": True, "products": True, "purchase": True},
        shop_type="regional",
    )
    assert "purchase" in domains
