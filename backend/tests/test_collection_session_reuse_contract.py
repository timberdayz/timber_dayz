import pytest


@pytest.mark.asyncio
async def test_load_or_bootstrap_session_prefers_existing_storage_state(monkeypatch):
    from modules.apps.collection_center import executor_v2

    existing = {"storage_state": {"cookies": [], "origins": []}}

    async def _fake_load(platform, account_id, max_age_days=30):
        return existing

    monkeypatch.setattr(executor_v2, "_load_session_async", _fake_load)
    monkeypatch.setattr(
        executor_v2,
        "_bootstrap_session_from_profile_sync",
        lambda platform, account_id, account_config=None: {"storage_state": {"unexpected": True}},
    )

    session_data = await executor_v2._load_or_bootstrap_session_async(
        "miaoshou",
        "acc-1",
        {"account_id": "acc-1"},
    )

    assert session_data == existing


@pytest.mark.asyncio
async def test_load_or_bootstrap_session_falls_back_to_profile_bootstrap(monkeypatch):
    from modules.apps.collection_center import executor_v2

    async def _fake_load(platform, account_id, max_age_days=30):
        return None

    monkeypatch.setattr(executor_v2, "_load_session_async", _fake_load)
    monkeypatch.setattr(
        executor_v2,
        "_bootstrap_session_from_profile_sync",
        lambda platform, account_id, account_config=None: {"storage_state": {"cookies": ["from_profile"]}},
    )

    session_data = await executor_v2._load_or_bootstrap_session_async(
        "miaoshou",
        "acc-1",
        {"account_id": "acc-1"},
    )

    assert session_data == {"storage_state": {"cookies": ["from_profile"]}}
