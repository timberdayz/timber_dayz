import pytest


@pytest.mark.asyncio
async def test_bootstrap_skips_when_lock_not_acquired(monkeypatch):
    from backend.services.data_pipeline import dashboard_bootstrap

    async def fake_inspect(_session):
        return {"ready": False}

    async def should_not_run(_session):
        raise AssertionError("bootstrap_dashboard_assets should not run without lock")

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(dashboard_bootstrap, "bootstrap_dashboard_assets", should_not_run)

    class _Scalar:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

    class _Session:
        def __init__(self):
            self.calls = []

        async def execute(self, stmt, params=None):
            self.calls.append(str(stmt))
            if "pg_try_advisory_lock" in str(stmt):
                return _Scalar(False)
            return _Scalar(None)

    session = _Session()
    report = await dashboard_bootstrap.bootstrap_dashboard_assets_if_needed(
        session, wait_for_lock=False
    )
    assert report["bootstrapped"] is False
    assert report["bootstrap_in_progress"] is True


@pytest.mark.asyncio
async def test_bootstrap_acquires_lock_and_unlocks(monkeypatch):
    from backend.services.data_pipeline import dashboard_bootstrap

    async def fake_inspect(_session):
        return {"ready": False}

    async def fake_bootstrap(_session):
        return {"ready": True, "run_id": "run_test"}

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(dashboard_bootstrap, "bootstrap_dashboard_assets", fake_bootstrap)

    class _Scalar:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

    class _Session:
        def __init__(self):
            self.calls = []

        async def execute(self, stmt, params=None):
            self.calls.append(str(stmt))
            if "pg_try_advisory_lock" in str(stmt):
                return _Scalar(True)
            return _Scalar(None)

    session = _Session()
    report = await dashboard_bootstrap.bootstrap_dashboard_assets_if_needed(
        session, wait_for_lock=False
    )
    assert report["bootstrapped"] is True
    assert report["run_id"] == "run_test"
    assert any("pg_advisory_unlock" in call for call in session.calls)


@pytest.mark.asyncio
async def test_bootstrap_waits_for_lock_in_deploy_mode(monkeypatch):
    from backend.services.data_pipeline import dashboard_bootstrap

    async def fake_inspect(_session):
        return {"ready": False}

    async def fake_bootstrap(_session):
        return {"ready": True}

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(dashboard_bootstrap, "bootstrap_dashboard_assets", fake_bootstrap)

    class _Scalar:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

    class _Session:
        def __init__(self):
            self.calls = []

        async def execute(self, stmt, params=None):
            self.calls.append(str(stmt))
            return _Scalar(None)

    session = _Session()
    report = await dashboard_bootstrap.bootstrap_dashboard_assets_if_needed(
        session, wait_for_lock=True
    )
    assert report["bootstrapped"] is True
    assert any("pg_advisory_lock" in call for call in session.calls)

