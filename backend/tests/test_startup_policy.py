from backend import main
import pytest


def test_development_defaults_disable_runtime_init_db(monkeypatch):
    monkeypatch.delenv("ENABLE_INIT_DB_ON_STARTUP", raising=False)

    assert main.should_init_db_on_startup("development") is False


def test_development_defaults_enable_runtime_dashboard_bootstrap(monkeypatch):
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    assert main.should_auto_bootstrap_dashboard_on_startup("development") is True


def test_production_defaults_disable_runtime_dashboard_bootstrap(monkeypatch):
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    assert main.should_auto_bootstrap_dashboard_on_startup("production") is False


@pytest.mark.asyncio
async def test_collect_dashboard_bootstrap_report_prefers_bootstrap_when_enabled(monkeypatch):
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    calls: list[str] = []

    class _Session:
        async def commit(self):
            calls.append("commit")

    class _SessionFactory:
        async def __aenter__(self):
            calls.append("enter")
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            calls.append("exit")

    async def _fake_bootstrap(session, *, wait_for_lock, module):
        assert wait_for_lock is True
        assert module == "all"
        calls.append("bootstrap")
        return {"ready": True, "bootstrapped": True}

    async def _fake_inspect(_session):
        calls.append("inspect")
        return {"ready": True}

    report = await main.collect_dashboard_bootstrap_report(
        "development",
        session_factory=_SessionFactory,
        inspect_assets=_fake_inspect,
        bootstrap_assets_if_needed=_fake_bootstrap,
    )

    assert report["startup_policy"] == "auto_bootstrap"
    assert calls == ["enter", "bootstrap", "commit", "exit"]
