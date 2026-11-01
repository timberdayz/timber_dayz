from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_load_or_bootstrap_session_prefers_existing_storage_state(monkeypatch):
    from modules.apps.collection_center import executor_v2

    existing = {"storage_state": {"cookies": [], "origins": []}}

    async def _fake_load(platform, account_id, max_age_days=30):
        return existing

    monkeypatch.setattr(executor_v2, "_load_session_async", _fake_load)
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session._bootstrap_session_from_profile_sync",
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
        "modules.apps.collection_center.runtime_session._bootstrap_session_from_profile_sync",
        lambda platform, account_id, account_config=None: {"storage_state": {"cookies": ["from_profile"]}},
    )

    session_data = await executor_v2._load_or_bootstrap_session_async(
        "miaoshou",
        "acc-1",
        {"account_id": "acc-1"},
    )

    assert session_data == {"storage_state": {"cookies": ["from_profile"]}}


def test_manual_storage_state_wins_over_existing_profile():
    """人工巡店保存的会话必须优先于持久 profile 目录被读取。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    # profile 目录非空（has_persistent_profile=True）但人工会话存在 -> 必须读人工会话
    assert CollectionExecutorV2._should_prefer_manual_storage_state(
        has_persistent_profile=True,
        has_manual_storage_state=True,
    )
    assert not CollectionExecutorV2._should_prefer_manual_storage_state(
        has_persistent_profile=True,
        has_manual_storage_state=False,
    )


def test_manual_storage_state_probe_uses_session_manager_path(monkeypatch, tmp_path):
    """人工会话的探测路径必须与 ``SessionManager.get_session_path`` 完全一致。

    路径规则不一致（原始 account_id vs 净化后的目录名）→ 采集侧读不到巡店面板
    保存的会话（spec D5 / D6）。
    """
    from modules.apps.collection_center import executor_v2
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    session_file = manager.get_session_path("shopee", "hongxikeji:main")
    session_file.write_text("{}", encoding="utf-8")

    assert executor_v2._manual_storage_state_exists("shopee", "hongxikeji:main") is True
    assert executor_v2._manual_storage_state_exists("shopee", "hongxikeji:other") is False


@pytest.mark.asyncio
async def test_open_runtime_bundle_auto_prefers_manual_session_over_persistent_profile(
    monkeypatch,
):
    """auto 模式下：已有持久 profile + 人工会话 → 必须走人工会话（spec D6 / A4）。"""
    from modules.apps.collection_center import executor_v2

    executor = executor_v2.CollectionExecutorV2()
    persistent_open = _AsyncRecorder(_FakeBundle("persistent-bundle"))
    storage_open = _AsyncRecorder(_FakeBundle("storage-bundle"))

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        persistent_open,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_storage_state_runtime_bundle",
        storage_open,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.runtime_profile_exists",
        lambda platform, session_owner_id: True,
    )
    monkeypatch.setattr(
        executor_v2,
        "_manual_storage_state_exists",
        lambda platform, account_id: True,
    )

    async def _fake_load_or_bootstrap(platform, account_id, account_config=None, **kwargs):
        return {
            "storage_state": {"cookies": [{"name": "sessionid"}], "origins": []},
            "metadata": {"manual_seeded": True, "protected": True},
        }

    monkeypatch.setattr(
        executor_v2,
        "_load_or_bootstrap_session_async",
        _fake_load_or_bootstrap,
    )

    bundle = await executor._open_runtime_bundle(
        session_runtime_mode="auto",
        browser=object(),
        browser_type=object(),
        platform="tiktok",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://seller.tiktok.com/login"},
        storage_state=None,
        launch_kwargs={"headless": True},
    )

    assert bundle is storage_open.result
    assert persistent_open.calls == []
    assert storage_open.calls, "人工会话存在时必须走 storage_state 通道"
    assert getattr(bundle, "session_source", None) == "manual_storage_state"


def test_executor_does_not_keep_duplicate_profile_bootstrap():
    """executor 侧不得再保留一份自己的 profile bootstrap（spec D6）。

    ``runtime_session._bootstrap_session_from_profile_sync`` 才有 TikTok 质量门禁；
    executor 侧那份副本没有 → 低质量 state 会被提升为正式会话。
    """
    from modules.apps.collection_center import executor_v2

    source = Path(executor_v2.__file__).read_text(encoding="utf-8")
    assert "def _bootstrap_session_from_profile_sync" not in source, (
        "executor 侧仍有一份自己的 _bootstrap_session_from_profile_sync（缺 TikTok 质量门禁），"
        "应改为复用 runtime_session 的实现"
    )


class _FakeBundle:
    """可承载运行时注解（session_source 等）的最小 bundle 替身。"""

    def __init__(self, name: str):
        self.name = name


class _AsyncRecorder:
    """记录 await 次数的最小异步替身。"""

    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result
