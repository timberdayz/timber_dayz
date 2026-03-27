from backend.services.active_collection_components import (
    is_active_component_name,
    is_archive_only_file,
    list_active_component_names,
)


def test_active_component_names_only_include_current_v2_live_set():
    assert list_active_component_names() == [
        "miaoshou/login",
        "miaoshou/orders_export",
    ]


def test_is_active_component_name_matches_only_whitelisted_v2_components():
    assert is_active_component_name("miaoshou/login") is True
    assert is_active_component_name("miaoshou/orders_export") is True
    assert is_active_component_name("shopee/orders_export") is False
    assert is_active_component_name("miaoshou/miaoshou_login") is False


def test_archive_only_file_detection_covers_archive_and_legacy_shapes():
    assert is_archive_only_file("modules/platforms/miaoshou/archive/login.py") is True
    assert is_archive_only_file("modules/platforms/miaoshou/components/login_v1_0_3.py") is False
    assert is_archive_only_file("modules/platforms/miaoshou/components/miaoshou_login.py") is True
    assert is_archive_only_file("modules/platforms/miaoshou/components/orders_export.py") is False
