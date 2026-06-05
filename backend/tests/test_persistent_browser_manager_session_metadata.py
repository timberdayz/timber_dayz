from __future__ import annotations

from types import SimpleNamespace

from modules.utils.persistent_browser_manager import PersistentBrowserManager


class _FakeContext:
    def __init__(self) -> None:
        self.pages = [object()]
        self.created_pages: list[object] = []

    def storage_state(self):  # noqa: ANN001
        return {"cookies": [{"name": "session"}], "origins": []}

    def new_page(self):  # noqa: ANN001
        page = SimpleNamespace(close=lambda: None)
        self.created_pages.append(page)
        return page


class _FakeSessionManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, dict]] = []

    def save_session(self, platform, account_id, storage_state, metadata=None):  # noqa: ANN001
        self.calls.append((platform, account_id, storage_state, metadata or {}))
        return True


def _manager_with_fake_session_manager() -> tuple[PersistentBrowserManager, _FakeSessionManager]:
    manager = PersistentBrowserManager.__new__(PersistentBrowserManager)
    fake_session_manager = _FakeSessionManager()
    manager.session_manager = fake_session_manager
    return manager, fake_session_manager


def test_save_context_state_keeps_automatic_metadata_by_default() -> None:
    manager, fake_session_manager = _manager_with_fake_session_manager()

    success = manager.save_context_state(_FakeContext(), "shopee", "shop-1")

    assert success is True
    _, _, storage_state, metadata = fake_session_manager.calls[0]
    assert storage_state == {"cookies": [{"name": "session"}], "origins": []}
    assert metadata["persistent_profile"] is True
    assert metadata["context_type"] == "persistent"
    assert "saved_at" in metadata
    assert "manual_seeded" not in metadata
    assert "protected" not in metadata


def test_save_context_state_merges_manual_session_metadata() -> None:
    manager, fake_session_manager = _manager_with_fake_session_manager()

    success = manager.save_context_state(
        _FakeContext(),
        "shopee",
        "shop-2",
        session_metadata={
            "quality_source": "manual",
            "manual_seeded": True,
            "protected": True,
        },
    )

    assert success is True
    _, _, _, metadata = fake_session_manager.calls[0]
    assert metadata["persistent_profile"] is True
    assert metadata["context_type"] == "persistent"
    assert "saved_at" in metadata
    assert metadata["quality_source"] == "manual"
    assert metadata["manual_seeded"] is True
    assert metadata["protected"] is True
