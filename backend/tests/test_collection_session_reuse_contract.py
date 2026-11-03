"""顺序采集路径的会话载体契约（Task 4.2：profile 是唯一载体）。

旧契约：人工巡店保存的会话（``data/sessions/**``）**优先于**持久 profile 目录。
Task 4.2 之后：正式采集**恒走持久 profile**（R1 真相源唯一）——
会话文件不再是载体，顺序路径不再读它，也不再从它 bootstrap。
"""

from pathlib import Path

import pytest


# Task 4.2 删除清单：这些 executor 侧入口必须**整体消失**。
_DEAD_EXECUTOR_HELPERS = (
    "_manual_storage_state_path",
    "_manual_storage_state_exists",
    "_load_or_bootstrap_session_async",
    "_should_prefer_manual_storage_state",
    "_prepare_runtime_page_bundle",
)


def test_executor_no_longer_has_session_file_entrypoints():
    """executor 侧不得再保留「读会话文件 / bootstrap / 人工会话优先」的入口。"""
    from modules.apps.collection_center import executor_v2

    source = Path(executor_v2.__file__).read_text(encoding="utf-8")
    for name in _DEAD_EXECUTOR_HELPERS:
        assert f"def {name}" not in source, f"executor 侧仍保留 {name}"
    # 会话文件读取入口也必须消失（只剩 Task 7 要处理的「登录后写盘」）
    assert "def _load_session_async" not in source, "executor 侧仍保留会话文件读取入口"


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


@pytest.mark.asyncio
async def test_open_runtime_bundle_auto_always_uses_persistent_profile(
    monkeypatch,
):
    """auto 模式下**恒走持久 profile**：人工会话文件存在也不例外（R1 真相源唯一）。

    旧契约是「人工巡店保存的会话优先于 profile 目录」（spec D6 / A4）；
    Task 4.2 之后会话文件整体废除 → 顺序路径只剩 profile 一个载体。
    """
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

    assert bundle is persistent_open.result
    assert persistent_open.calls, "正式采集必须走 profile 通道"
    assert storage_open.calls == [], "不得再退回 storage_state 扇出通道"
    assert getattr(bundle, "session_source", None) == "persistent_profile"


@pytest.mark.asyncio
async def test_open_runtime_bundle_never_reads_session_file(monkeypatch):
    """打开 runtime bundle 的过程中**不得读会话文件**（profile 是唯一载体）。

    这是「不读会话文件」这条验收口径的守门用例：
    只要有人把「读会话文件 / bootstrap」重新接回顺序路径，这里立刻变红。
    """
    from modules.apps.collection_center import executor_v2

    executor = executor_v2.CollectionExecutorV2()

    def _boom(*args, **kwargs):
        raise AssertionError("顺序采集路径不得读会话文件")

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.load_session",
        _boom,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.load_runtime_session_candidate",
        _boom,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        _AsyncRecorder(_FakeBundle("persistent-bundle")),
    )

    bundle = await executor._open_runtime_bundle(
        session_runtime_mode="auto",
        browser=object(),
        browser_type=object(),
        platform="shopee",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://seller.shopee.cn"},
        storage_state=None,
        launch_kwargs={"headless": True},
    )

    assert getattr(bundle, "session_source", None) == "persistent_profile"


@pytest.mark.asyncio
async def test_open_runtime_bundle_rejects_storage_state_fanout_mode():
    """显式请求 storage_state 扇出必须给出清晰错误（该模式已废除）。"""
    from modules.apps.collection_center import executor_v2

    executor = executor_v2.CollectionExecutorV2()

    with pytest.raises(ValueError) as excinfo:
        await executor._open_runtime_bundle(
            session_runtime_mode="storage_state_fanout",
            browser=object(),
            browser_type=object(),
            platform="shopee",
            session_owner_id="main-1",
            runtime_account={"login_url": "https://seller.shopee.cn"},
            storage_state={"cookies": [], "origins": []},
            launch_kwargs={"headless": True},
        )

    message = str(excinfo.value)
    assert "profile" in message
    assert "storage_state" in message


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
