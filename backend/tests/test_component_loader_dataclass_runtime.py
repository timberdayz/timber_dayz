from modules.apps.collection_center.component_loader import ComponentLoader


def test_component_loader_supports_dataclass_python_components():
    loader = ComponentLoader(hot_reload=True)

    component_class = loader.load_python_component_from_path(
        file_path="modules/platforms/miaoshou/components/orders_shopee_export.py",
        project_root="F:\\Vscode\\python_programme\\AI_code\\xihong_erp",
        platform="miaoshou",
        component_type="export",
    )

    assert component_class.__name__ == "MiaoshouOrdersShopeeExport"
