from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.routers.component_versions import save_test_history, save_test_history_sync


class _FakeSyncDB:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _FakeAsyncDB:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _test_result():
    return SimpleNamespace(
        status=SimpleNamespace(value="failed"),
        duration_ms=123.0,
        steps_total=1,
        steps_passed=0,
        steps_failed=1,
        error="boom",
        step_results=[
            SimpleNamespace(
                step_id="step-1",
                action="Execute login",
                status=SimpleNamespace(value="failed"),
                duration_ms=123.0,
                error="boom",
            )
        ],
    )


def test_save_test_history_sync_sets_tested_at():
    db = _FakeSyncDB()

    save_test_history_sync(
        db=db,
        component_name="miaoshou/login",
        platform="miaoshou",
        account_id="acc-1",
        test_result=_test_result(),
        version_id=83,
        component_version="1.0.0",
    )

    assert db.committed is True
    assert db.rolled_back is False
    assert db.added
    assert db.added[0].tested_at is not None


@pytest.mark.asyncio
async def test_save_test_history_async_sets_tested_at():
    db = _FakeAsyncDB()

    await save_test_history(
        db=db,
        component_name="miaoshou/login",
        platform="miaoshou",
        account_id="acc-1",
        test_result=_test_result(),
        version_id=83,
        component_version="1.0.0",
    )

    assert db.committed is True
    assert db.rolled_back is False
    assert db.added
    assert db.added[0].tested_at is not None
