import importlib


def test_field_mapping_router_no_longer_exposes_legacy_template_routes():
    module = importlib.import_module("backend.routers.field_mapping")
    paths = {route.path for route in module.router.routes}

    assert "/save-template" not in paths
    assert "/apply-template" not in paths
