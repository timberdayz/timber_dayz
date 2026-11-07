import pytest


def _drifted_report() -> dict:
    """一份「模块处于 drift」的检查结果。

    ``bootstrap_dashboard_assets_if_needed`` 会按模块逐个看状态，
    报告里必须带 ``modules``（旧桩只返回 ``{"ready": False}`` ⇒ KeyError）。
    """
    from backend.services.data_pipeline import dashboard_bootstrap

    return {
        "ready": False,
        "modules": {
            module_name: {"status": "drift", "ready": False}
            for module_name in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
        },
    }


@pytest.mark.asyncio
async def test_bootstrap_skips_when_lock_not_acquired(monkeypatch):
    from backend.services.data_pipeline import dashboard_bootstrap

    async def fake_inspect(_session):
        return _drifted_report()

    async def should_not_run(_session, **_kwargs):
        raise AssertionError("bootstrap_dashboard_assets should not run without lock")

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(
        dashboard_bootstrap, "bootstrap_dashboard_assets", should_not_run
    )

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
        return _drifted_report()

    async def fake_bootstrap(_session, **_kwargs):
        return {"ready": True, "run_id": "run_test"}

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(
        dashboard_bootstrap, "bootstrap_dashboard_assets", fake_bootstrap
    )

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
async def test_bootstrap_deploy_mode_zeroes_statement_timeout_before_locking(
    monkeypatch,
):
    """部署模式：先把 ``statement_timeout`` 归零，再轮询等锁。

    等锁可能要很久（另一个 bootstrap 正在重建视图 ⇒ 排他锁）⇒
    语句超时必须先归零，否则「等锁」本身会被超时打断。
    """
    from backend.services.data_pipeline import dashboard_bootstrap

    async def fake_inspect(_session):
        return _drifted_report()

    async def fake_bootstrap(_session, **_kwargs):
        return {"ready": True}

    monkeypatch.setattr(dashboard_bootstrap, "inspect_dashboard_assets", fake_inspect)
    monkeypatch.setattr(
        dashboard_bootstrap, "bootstrap_dashboard_assets", fake_bootstrap
    )

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
        session, wait_for_lock=True
    )
    assert report["bootstrapped"] is True
    assert any("statement_timeout = 0" in call for call in session.calls)
    assert any("pg_try_advisory_lock" in call for call in session.calls)
