import importlib


def _reload_main(monkeypatch, runtime_mode: str):
    import backend.main as main_module

    monkeypatch.setenv("APP_RUNTIME_MODE", runtime_mode)
    reloaded = importlib.reload(main_module)
    return reloaded


def _paths_for(module):
    return {route.path for route in module.app.routes if hasattr(route, "path")}


def test_production_mode_exposes_dashboard_but_not_collection(monkeypatch):
    module = _reload_main(monkeypatch, "production")
    paths = _paths_for(module)

    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/reference/shop-directory" in paths
    assert "/api/shop-accounts" in paths
    assert "/api/collection/configs" not in paths


def test_collector_mode_exposes_collection_but_not_dashboard(monkeypatch):
    module = _reload_main(monkeypatch, "collector")
    paths = _paths_for(module)

    assert "/api/collection/configs" in paths
    assert "/api/dashboard/business-overview/kpi" not in paths


def test_local_collector_mode_exposes_both_collection_and_dashboard(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ROLE", "local")
    module = _reload_main(monkeypatch, "collector")
    paths = _paths_for(module)

    assert "/api/collection/configs" in paths
    assert "/api/dashboard/business-overview/kpi" in paths


def test_development_mode_exposes_both_collector_and_dashboard(monkeypatch):
    module = _reload_main(monkeypatch, "development")
    paths = _paths_for(module)

    assert "/api/collection/configs" in paths
    assert "/api/dashboard/business-overview/kpi" in paths
