from backend.services.active_collection_components import (
    _discover_active_component_names,
    is_active_component_name,
    is_archive_only_file,
    list_active_component_names,
)


def test_discover_active_component_names_uses_supported_platform_canonical_files(tmp_path):
    project_root = tmp_path
    (project_root / "modules" / "platforms" / "shopee" / "components").mkdir(parents=True)
    (project_root / "modules" / "platforms" / "miaoshou" / "components").mkdir(parents=True)
    (project_root / "modules" / "platforms" / "amazon" / "components").mkdir(parents=True)

    (project_root / "modules" / "platforms" / "shopee" / "components" / "login.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "shopee" / "components" / "orders_export.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "shopee" / "components" / "orders_config.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "miaoshou" / "components" / "login.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "miaoshou" / "components" / "orders_shopee_export.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "miaoshou" / "components" / "orders_tiktok_export.py").write_text("", encoding="utf-8")
    (project_root / "modules" / "platforms" / "amazon" / "components" / "login.py").write_text("", encoding="utf-8")

    assert _discover_active_component_names(
        project_root=project_root,
        supported_platforms=("shopee", "miaoshou", "tiktok"),
    ) == [
        "miaoshou/login",
        "miaoshou/orders_shopee_export",
        "miaoshou/orders_tiktok_export",
        "shopee/login",
        "shopee/orders_export",
    ]


def test_active_component_names_include_current_supported_canonical_components():
    names = list_active_component_names()

    assert "miaoshou/login" in names
    assert "miaoshou/orders_shopee_export" in names
    assert "miaoshou/orders_tiktok_export" in names
    assert "shopee/login" in names
    assert "amazon/login" not in names


def test_is_active_component_name_matches_current_canonical_components():
    assert is_active_component_name("miaoshou/login") is True
    assert is_active_component_name("miaoshou/orders_shopee_export") is True
    assert is_active_component_name("miaoshou/orders_tiktok_export") is True
    assert is_active_component_name("shopee/login") is True
    assert is_active_component_name("amazon/login") is False
    assert is_active_component_name("miaoshou/miaoshou_login") is False


def test_archive_only_file_detection_covers_archive_and_legacy_shapes():
    assert is_archive_only_file("modules/platforms/miaoshou/archive/login.py") is True
    assert is_archive_only_file("modules/platforms/miaoshou/components/login_v1_0_3.py") is False
    assert is_archive_only_file("modules/platforms/miaoshou/components/miaoshou_login.py") is True
    assert is_archive_only_file("modules/platforms/miaoshou/components/orders_shopee_export.py") is False
    assert is_archive_only_file("modules/platforms/miaoshou/components/orders_export_base.py") is False
