import importlib
from pathlib import Path


def test_environment_examples_document_metabase_proxy_flag():
    for path_str in (".env.example", "env.development.example", "env.production.example"):
        text = Path(path_str).read_text(encoding="utf-8")
        assert "ENABLE_METABASE_PROXY=" in text


def test_readme_documents_postgresql_dashboard_and_legacy_metabase():
    text = Path("README.md").read_text(encoding="utf-8", errors="replace")
    assert "PostgreSQL Dashboard" in text
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER" in text
    assert "Metabase" in text
    assert "legacy" in text.lower()


def test_agent_start_here_marks_metabase_as_legacy_fallback():
    text = Path("docs/AGENT_START_HERE.md").read_text(encoding="utf-8", errors="replace")
    assert "PostgreSQL Dashboard" in text
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER" in text
    assert "Metabase" in text
    assert "legacy" in text.lower()


def test_main_disables_metabase_proxy_by_default(monkeypatch):
    import backend.main as main_module

    monkeypatch.delenv("ENABLE_METABASE_PROXY", raising=False)
    reloaded = importlib.reload(main_module)
    paths = {route.path for route in reloaded.app.routes if hasattr(route, "path")}

    assert "/api/metabase/health" not in paths

    importlib.reload(main_module)


def test_main_can_enable_metabase_proxy(monkeypatch):
    import backend.main as main_module

    monkeypatch.setenv("ENABLE_METABASE_PROXY", "true")
    reloaded = importlib.reload(main_module)
    paths = {route.path for route in reloaded.app.routes if hasattr(route, "path")}

    assert "/api/metabase/health" in paths

    monkeypatch.delenv("ENABLE_METABASE_PROXY", raising=False)
    importlib.reload(main_module)
