from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.ensure_local_dev_admin import (
    LocalDevAdminConfig,
    ensure_local_dev_admin,
    load_local_dev_admin_config,
)


def test_enabled_local_admin_bootstrap_requires_password():
    with pytest.raises(ValueError, match="LOCAL_DEV_ADMIN_PASSWORD"):
        load_local_dev_admin_config({"LOCAL_DEV_BOOTSTRAP_ADMIN": "true"})


def test_local_admin_bootstrap_is_disabled_by_default():
    assert load_local_dev_admin_config({}) is None


@pytest.mark.asyncio
async def test_existing_local_admin_is_never_reset():
    existing_user = SimpleNamespace(username="xihong")
    db = SimpleNamespace(execute=None)

    async def execute(_statement):
        return SimpleNamespace(scalar_one_or_none=lambda: existing_user)

    db.execute = execute
    config = LocalDevAdminConfig("xihong", "secret-value", "xihong@local.test")

    result = await ensure_local_dev_admin(db, config, lambda _password: "hash")

    assert result == "existing"
    assert not hasattr(db, "add")
    assert config.password not in result


@pytest.mark.asyncio
async def test_missing_local_admin_is_created_without_returning_password(monkeypatch):
    from scripts import ensure_local_dev_admin as module

    admin_role = SimpleNamespace(role_id=1)
    results = iter(
        [
            SimpleNamespace(scalar_one_or_none=lambda: None),
            SimpleNamespace(scalar_one_or_none=lambda: admin_role),
        ]
    )

    class FakeDb:
        def __init__(self):
            self.added = []
            self.flushed = 0

        async def execute(self, _statement):
            return next(results)

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            self.flushed += 1

    class FakeUser:
        class username:
            def __eq__(self, _value):
                return None

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.roles = []

    monkeypatch.setattr(module, "DimUser", FakeUser)
    monkeypatch.setattr(
        module,
        "select",
        lambda _model: SimpleNamespace(where=lambda _condition: None),
    )
    db = FakeDb()
    password = "secret-value"
    result = await ensure_local_dev_admin(
        db,
        LocalDevAdminConfig("xihong", password, "xihong@local.test"),
        lambda value: f"hashed:{value}",
    )

    assert result == "created"
    assert db.added[0].username == "xihong"
    assert db.added[0].password_hash == "hashed:secret-value"
    assert db.added[0].roles == [admin_role]
    assert db.flushed == 1
    assert password not in result
