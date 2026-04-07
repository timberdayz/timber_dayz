from pathlib import Path

from backend.routers.component_versions import _derive_python_test_component_name


def test_derive_python_test_component_name_preserves_domain_export_name() -> None:
    assert _derive_python_test_component_name(
        version_component_name="shopee/products_export",
        logical_component="export",
        component_path=Path("modules/platforms/shopee/components/products_export.py"),
    ) == "products_export"


def test_derive_python_test_component_name_keeps_login_logical_name() -> None:
    assert _derive_python_test_component_name(
        version_component_name="shopee/login",
        logical_component="login",
        component_path=Path("modules/platforms/shopee/components/login.py"),
    ) == "login"
