"""``persistent_browser_manager.save_context_state`` 的新契约（Task 7）。

会话文件体系废除后，这个方法**不再写任何会话文件**：登录态只由 Chromium
持久 profile 承载，而 Chromium 只在 profile context **正常关闭**时把 cookie /
localStorage 刷回 profile 目录（R7）。

所以「保存会话」这一步的落地方式只剩一个：**正常关闭 profile context**。
"""

from __future__ import annotations

from modules.utils.persistent_browser_manager import PersistentBrowserManager


class _FakeContext:
    def __init__(self) -> None:
        self.pages = [object()]
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeSessionManager:
    """旧实现依赖的会话文件写入接口 —— Task 7 后不应再被调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def save_session(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append((args, kwargs))
        return True


def _manager_with_fake_session_manager() -> tuple[PersistentBrowserManager, _FakeSessionManager]:
    manager = PersistentBrowserManager.__new__(PersistentBrowserManager)
    fake_session_manager = _FakeSessionManager()
    manager.session_manager = fake_session_manager
    return manager, fake_session_manager


def test_save_context_state_does_not_write_session_file() -> None:
    """会话文件已废除：这个方法不得再调用任何会话写入接口。"""
    manager, fake_session_manager = _manager_with_fake_session_manager()
    context = _FakeContext()

    ok = manager.save_context_state(context, "shopee", "shop-1")

    assert ok is True
    assert fake_session_manager.calls == [], "会话文件已废除，不得再写"


def test_save_context_state_closes_profile_context() -> None:
    """登录态要落到 profile，Chromium 必须被正常关闭（R7）。"""
    manager, _ = _manager_with_fake_session_manager()
    context = _FakeContext()

    manager.save_context_state(context, "shopee", "shop-1")

    assert context.closed is True


def test_save_context_state_tolerates_already_closed_context() -> None:
    """重复关闭（先关后 close_context）不得抛错。"""
    manager, _ = _manager_with_fake_session_manager()

    class _ClosedContext:
        pages = [object()]

        def close(self):
            raise RuntimeError("Target page, context or browser has been closed")

    ok = manager.save_context_state(_ClosedContext(), "shopee", "shop-1")

    assert ok is True
