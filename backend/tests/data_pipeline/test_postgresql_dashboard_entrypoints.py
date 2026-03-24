import importlib
from pathlib import Path


def test_environment_examples_no_longer_document_metabase_proxy_flag():
    for path_str in (".env.example", "env.development.example", "env.production.example"):
        text = Path(path_str).read_text(encoding="utf-8")
        assert "ENABLE_METABASE_PROXY=" not in text


def test_readme_documents_postgresql_dashboard_without_runtime_metabase_fallback():
    text = Path("README.md").read_text(encoding="utf-8", errors="replace")
    assert "PostgreSQL Dashboard" in text
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER" not in text
    assert "--with-metabase" not in text


def test_agent_start_here_no_longer_describes_runtime_metabase_fallback():
    text = Path("docs/AGENT_START_HERE.md").read_text(encoding="utf-8", errors="replace")
    assert "PostgreSQL Dashboard" in text
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER" not in text
    assert "--with-metabase" not in text


def test_main_never_exposes_metabase_proxy(monkeypatch):
    import backend.main as main_module

    monkeypatch.delenv("ENABLE_METABASE_PROXY", raising=False)
    monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
    reloaded = importlib.reload(main_module)
    paths = {route.path for route in reloaded.app.routes if hasattr(route, "path")}

    assert "/api/metabase/health" not in paths
    dashboard_route = next(
        route
        for route in reloaded.app.routes
        if getattr(route, "path", None) == "/api/dashboard/business-overview/kpi"
    )
    assert dashboard_route.endpoint.__module__ == "backend.routers.dashboard_api_postgresql"

    importlib.reload(main_module)


def test_main_exposes_data_pipeline_routes():
    import backend.main as main_module

    reloaded = importlib.reload(main_module)
    paths = {route.path for route in reloaded.app.routes if hasattr(route, "path")}

    assert "/api/data-pipeline/status" in paths
    assert "/api/data-pipeline/freshness" in paths
    assert "/api/data-pipeline/lineage" in paths

    importlib.reload(main_module)


def test_main_defaults_to_postgresql_dashboard_router(monkeypatch):
    import backend.main as main_module

    monkeypatch.delenv("USE_POSTGRESQL_DASHBOARD_ROUTER", raising=False)
    reloaded = importlib.reload(main_module)

    dashboard_route = next(
        route
        for route in reloaded.app.routes
        if getattr(route, "path", None) == "/api/dashboard/business-overview/kpi"
    )

    assert dashboard_route.endpoint.__module__ == "backend.routers.dashboard_api_postgresql"

    importlib.reload(main_module)
