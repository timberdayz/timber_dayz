from __future__ import annotations

from modules.apps.collection_center.handlers import RecordingWizardHandler


class _FakePage:
    pass


class _FakeContext:
    def new_page(self):  # noqa: ANN001
        return _FakePage()


class _FakePersistentBrowserManager:
    instances: list["_FakePersistentBrowserManager"] = []

    def __init__(self, playwright):  # noqa: ANN001
        self.playwright = playwright
        self.calls: list[tuple[str, str, dict | None]] = []
        self.closed: list[tuple[str, str]] = []
        self.context = _FakeContext()
        self.__class__.instances.append(self)

    def get_or_create_persistent_context(self, platform, account_id, account):  # noqa: ANN001
        return self.context

    def save_context_state(self, context, platform, account_id, session_metadata=None):  # noqa: ANN001
        self.calls.append((platform, account_id, session_metadata))
        return True

    def close_context(self, platform, account_id):  # noqa: ANN001
        self.closed.append((platform, account_id))


class _FakeSyncPlaywright:
    def __enter__(self):  # noqa: ANN001
        return object()

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False


def _assert_manual_metadata(payload: dict | None) -> None:
    assert payload == {
        "quality_source": "manual",
        "manual_seeded": True,
        "protected": True,
    }


def test_data_collection_recording_marks_saved_session_as_manual(monkeypatch) -> None:
    _FakePersistentBrowserManager.instances.clear()
    handler = RecordingWizardHandler()

    monkeypatch.setattr(
        "modules.utils.persistent_browser_manager.PersistentBrowserManager",
        _FakePersistentBrowserManager,
    )
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _FakeSyncPlaywright())
    monkeypatch.setattr(
        "modules.apps.collection_center.handlers.resolve_account_session_id",
        lambda account: "shop-1",
    )
    monkeypatch.setattr(
        RecordingWizardHandler,
        "_execute_collection_recording",
        lambda self, playwright, page, account, platform, login_url, data_type_key=None: None,
    )

    handler._execute_data_collection_recording(
        account={"account_id": "shop-1", "store_name": "Shopee 1"},
        platform="shopee",
        login_url="https://seller.shopee.cn/account/signin",
        data_type_key="orders",
    )

    manager = _FakePersistentBrowserManager.instances[0]
    assert manager.calls
    platform, account_id, metadata = manager.calls[0]
    assert platform == "shopee"
    assert account_id == "shop-1"
    _assert_manual_metadata(metadata)


def test_full_process_recording_marks_saved_session_as_manual(monkeypatch) -> None:
    _FakePersistentBrowserManager.instances.clear()
    handler = RecordingWizardHandler()

    monkeypatch.setattr(
        "modules.utils.persistent_browser_manager.PersistentBrowserManager",
        _FakePersistentBrowserManager,
    )
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _FakeSyncPlaywright())
    monkeypatch.setattr(
        "modules.apps.collection_center.handlers.resolve_account_session_id",
        lambda account: "shop-2",
    )
    monkeypatch.setattr(
        RecordingWizardHandler,
        "_execute_complete_recording",
        lambda self, page, account, platform, login_url: None,
    )

    handler._execute_full_process_recording(
        account={"account_id": "shop-2", "store_name": "Shopee 2"},
        platform="shopee",
        login_url="https://seller.shopee.cn/account/signin",
        data_type_key="orders",
    )

    manager = _FakePersistentBrowserManager.instances[0]
    assert manager.calls
    platform, account_id, metadata = manager.calls[0]
    assert platform == "shopee"
    assert account_id == "shop-2"
    _assert_manual_metadata(metadata)
