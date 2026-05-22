from backend import main


def test_development_defaults_disable_runtime_init_db(monkeypatch):
    monkeypatch.delenv("ENABLE_INIT_DB_ON_STARTUP", raising=False)

    assert main.should_init_db_on_startup("development") is False


def test_development_defaults_disable_runtime_dashboard_bootstrap(monkeypatch):
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    assert main.should_auto_bootstrap_dashboard_on_startup("development") is False


def test_production_defaults_disable_runtime_dashboard_bootstrap(monkeypatch):
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    assert main.should_auto_bootstrap_dashboard_on_startup("production") is False

