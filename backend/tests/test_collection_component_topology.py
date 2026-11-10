from pathlib import Path

from backend.services.collection_component_topology import (
    build_component_name_from_filename,
    is_canonical_component_filename,
    is_legacy_component_filename,
)
from backend.domains.collection.routers.component_versions import (
    CANONICAL_COMPONENT_FILES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_component_files_all_exist_on_disk():
    """canonical 清单里的每个文件都必须真实存在于组件目录里。

    为什么要有这条
    --------------
    组件目录会随重构增删文件（例如「各平台订单统一走妙手采集」把
    ``shopee/orders_export.py`` 删掉，订单导出改到
    ``miaoshou/orders_shopee_export``）。清单若没跟着改，就会留下
    「名单说有、磁盘上没有」的幽灵条目 —— 既误导人，也可能让 fallback
    去加载不存在的文件。

    ⇒ 组件目录变了而清单没变，在这里变红。
    """
    missing = []
    for platform, filenames in sorted(CANONICAL_COMPONENT_FILES.items()):
        for filename in sorted(filenames):
            path = (
                PROJECT_ROOT
                / "modules"
                / "platforms"
                / platform
                / "components"
                / filename
            )
            if not path.is_file():
                missing.append(f"{platform}/{filename}")
    assert (
        not missing
    ), "canonical 组件清单里的文件在仓库里不存在: {missing} —— " "组件目录已变，清单没跟着变".format(
        missing=", ".join(missing)
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
    assert (
        build_component_name_from_filename("miaoshou", "login.py") == "miaoshou/login"
    )
    assert (
        build_component_name_from_filename("miaoshou", "orders_shopee_export.py")
        == "miaoshou/orders_shopee_export"
    )
    assert (
        build_component_name_from_filename("tiktok", "services_agent_export.py")
        == "tiktok/services_agent_export"
    )
