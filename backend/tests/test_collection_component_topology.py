from backend.services.collection_component_topology import (
    build_component_name_from_filename,
    is_canonical_component_filename,
    is_legacy_component_filename,
)


def test_fixed_slots_are_canonical():
    assert is_canonical_component_filename("login.py") is True
    assert is_canonical_component_filename("navigation.py") is True
    assert is_canonical_component_filename("date_picker.py") is True
    assert is_canonical_component_filename("shop_switch.py") is True
    assert is_canonical_component_filename("filters.py") is True


def test_domain_export_files_are_canonical():
    assert is_canonical_component_filename("orders_export.py") is True
    assert is_canonical_component_filename("orders_shopee_export.py") is True
    assert is_canonical_component_filename("orders_tiktok_export.py") is True
    assert is_canonical_component_filename("products_export.py") is True
    assert is_canonical_component_filename("services_agent_export.py") is True


def test_config_helper_and_versioned_files_are_not_canonical():
    assert is_canonical_component_filename("orders_config.py") is False
    assert is_canonical_component_filename("overlay_guard.py") is False
    assert is_canonical_component_filename("login_v1_0_3.py") is False
    assert is_canonical_component_filename("export.py") is False
    assert is_canonical_component_filename("miaoshou_login.py") is False


def test_legacy_component_filename_detection():
    assert is_legacy_component_filename("login_v1_0_3.py") is True
    assert is_legacy_component_filename("miaoshou_login.py") is True
    assert is_legacy_component_filename("orders_config.py") is False
    assert is_legacy_component_filename("orders_export.py") is False


def test_build_component_name_from_filename():
    assert build_component_name_from_filename("miaoshou", "login.py") == "miaoshou/login"
    assert (
        build_component_name_from_filename("miaoshou", "orders_shopee_export.py")
        == "miaoshou/orders_shopee_export"
    )
    assert (
        build_component_name_from_filename("tiktok", "services_agent_export.py")
        == "tiktok/services_agent_export"
    )
