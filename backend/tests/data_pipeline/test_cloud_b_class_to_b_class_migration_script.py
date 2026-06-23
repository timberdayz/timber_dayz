from pathlib import Path

import pytest


def test_cloud_b_class_to_b_class_migration_script_targets_expected_schemas_and_refreshes():
    text = Path("scripts/migrate_cloud_b_class_to_b_class.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "cloud_b_class" in text
    assert 'schema_name="b_class"' in text or 'schema_name = "b_class"' in text
    assert "ON CONFLICT" in text
    assert "refresh_dashboard_materialization_assets" in text


@pytest.mark.asyncio
async def test_cloud_b_class_to_b_class_migration_refresh_updates_dashboard_asset_state(monkeypatch):
    import scripts.migrate_cloud_b_class_to_b_class as script

    calls = []

    class FakeEngine:
        async def dispose(self):
            calls.append(("dispose",))

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            calls.append(("commit",))

    def fake_create_async_engine(url):
        calls.append(("engine", url))
        return FakeEngine()

    def fake_async_sessionmaker(engine, expire_on_commit):
        calls.append(("sessionmaker", engine, expire_on_commit))

        def _factory():
            return FakeSession()

        return _factory

    async def fake_refresh_dashboard_materialization_assets(session, *, module):
        calls.append(("refresh", session, module))
        return {"ready": True, "module": module}

    monkeypatch.setattr(script, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(script, "async_sessionmaker", fake_async_sessionmaker)
    monkeypatch.setattr(
        script,
        "refresh_dashboard_materialization_assets",
        fake_refresh_dashboard_materialization_assets,
    )

    result = await script.refresh_dashboard_assets("postgresql://user:pass@localhost/db")

    assert result == {"ready": True, "module": "all"}
    assert ("refresh", calls[2][1], "all") in calls
    assert ("commit",) in calls
    assert ("dispose",) in calls
