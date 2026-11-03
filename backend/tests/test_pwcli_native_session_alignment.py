from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from modules.utils import pwcli_native


def test_resolve_session_platform_uses_session_prefix() -> None:
    assert pwcli_native.resolve_session_platform("tiktok-explore") == "tiktok"
    assert pwcli_native.resolve_session_platform("shopee-products-export") == "shopee"
    assert pwcli_native.resolve_session_platform("custom-debug") is None


def test_resolve_default_profile_dir_uses_platform_profile_root_without_account_id() -> None:
    path = pwcli_native.resolve_default_profile_dir("tiktok-explore", None)

    assert path == pwcli_native.REPO_ROOT / "output" / "playwright" / "profiles" / "tiktok"


def test_resolve_default_profile_dir_uses_runtime_account_profile_with_account_id() -> None:
    path = pwcli_native.resolve_default_profile_dir("tiktok-explore", "Tiktok 2店")

    assert path == pwcli_native.REPO_ROOT / "profiles" / "tiktok" / "Tiktok2店"


def test_load_storage_state_payload_accepts_wrapped_session_manager_format(tmp_path: Path) -> None:
    payload_path = tmp_path / "storage_state.json"
    payload_path.write_text(
        '{"platform":"tiktok","account_id":"acc-1","storage_state":{"cookies":[{"name":"a"}],"origins":[]}}',
        encoding="utf-8",
    )

    payload = pwcli_native.load_storage_state_payload(payload_path)

    assert payload == {"cookies": [{"name": "a"}], "origins": []}


def test_maybe_load_default_storage_state_returns_false_for_blank_json_file(tmp_path: Path) -> None:
    payload_path = tmp_path / "storage_state.json"
    payload_path.write_text("", encoding="utf-8")

    loaded = pwcli_native.maybe_load_default_storage_state(
        object(),
        {"default_state_path": str(payload_path)},
    )

    assert loaded is False


def test_parse_open_args_accepts_account_id_option() -> None:
    url, headed, profile_dir, account_id, proxy_server = pwcli_native.parse_open_args(
        ["https://seller.tiktokglobalshop.com/", "--headed", "--account-id", "Tiktok 2店"]
    )

    assert url == "https://seller.tiktokglobalshop.com/"
    assert headed is True
    assert profile_dir is None
    assert account_id == "Tiktok 2店"
    assert proxy_server is None


def test_parse_open_args_accepts_proxy_server_option() -> None:
    _url, _headed, _profile_dir, _account_id, proxy_server = pwcli_native.parse_open_args(
        [
            "https://seller.tiktokglobalshop.com/",
            "--account-id",
            "Tiktok 2店",
            "--proxy-server",
            "http://10.0.0.9:8080",
        ]
    )

    assert proxy_server == "http://10.0.0.9:8080"


def test_proxy_credentials_are_read_from_environment(monkeypatch) -> None:
    """代理凭据不得进命令行（进程列表可见），只走环境变量。"""
    monkeypatch.setenv("PWCLI_PROXY_USERNAME", "proxy-user")
    monkeypatch.setenv("PWCLI_PROXY_PASSWORD", "proxy-pass")

    assert pwcli_native.resolve_proxy_credentials() == ("proxy-user", "proxy-pass")


def test_pw_open_wrapper_can_forward_account_id_to_native_pwcli() -> None:
    source = Path("scripts/pw-open.ps1").read_text(encoding="utf-8")

    assert "AccountId" in source
    assert "--account-id" in source


def test_resolve_default_profile_dir_is_repo_root_anchored_even_when_cwd_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo_root.mkdir()
    elsewhere.mkdir()
    monkeypatch.setattr(pwcli_native, "REPO_ROOT", repo_root)
    monkeypatch.chdir(elsewhere)

    path = pwcli_native.resolve_default_profile_dir("tiktok-explore", "Tiktok 2店")

    assert path == repo_root / "profiles" / "tiktok" / "Tiktok2店"


def test_resolve_default_state_config_does_not_expose_session_file_for_account_level() -> None:
    """账号级巡店不得再有会话文件路径。

    否则 ``data/sessions`` 里的过期 cookie 会被注入进新 profile（违反 R1/R4），
    而且 Task 7 删掉 ``safe_session_account_dirname`` 后这里会直接 ImportError。
    """
    metadata = pwcli_native.resolve_default_state_config("tiktok-explore", "Tiktok 2店")

    assert "default_state_path" not in metadata
    assert "default_state_mode" not in metadata
    assert metadata["account_id"] == "Tiktok 2店"


def test_resolve_default_state_config_keeps_raw_json_for_platform_level() -> None:
    """平台级（无账号）的人工导出能力保留。"""
    metadata = pwcli_native.resolve_default_state_config("tiktok-explore", None)

    assert metadata["default_state_mode"] == "raw_json"
    assert Path(metadata["default_state_path"]).name == "tiktok.json"


def test_account_level_open_does_not_inject_legacy_storage_state() -> None:
    """账号级巡店不得把旧会话文件注入 profile。"""
    metadata = pwcli_native.resolve_default_state_config("tiktok-explore", "acc-1")

    assert pwcli_native.maybe_load_default_storage_state(object(), metadata) is False


class _ConsolePage:
    url = "https://example.com"

    def __init__(self, *, title_error: Exception | None = None, eval_error: Exception | None = None) -> None:
        self._title_error = title_error
        self._eval_error = eval_error

    def evaluate(self, script):  # noqa: ANN001
        if self._eval_error is not None:
            raise self._eval_error
        return []

    def title(self):
        if self._title_error is not None:
            raise self._title_error
        return "Example"


def test_page_summary_tolerates_title_navigation_errors() -> None:
    page = _ConsolePage(title_error=RuntimeError("Execution context was destroyed"))

    summary = pwcli_native.page_summary(page)

    assert "Page URL: https://example.com" in summary
    assert "Page Title: (unavailable during navigation)" in summary


def test_page_summary_tolerates_console_buffer_navigation_errors() -> None:
    page = _ConsolePage(eval_error=RuntimeError("Execution context was destroyed"))

    summary = pwcli_native.page_summary(page)

    assert "Page URL: https://example.com" in summary
    assert "Page Title: Example" in summary


def test_save_default_storage_state_from_context_does_not_write_session_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """``session_manager`` 分支必须不再写会话文件（profile 是登录态唯一载体）。"""
    saved = Mock()

    class _FakeSessionManager:
        def __init__(self, base_path=None):  # noqa: ANN001
            self.base_path = base_path

        def save_session(self, platform, account_id, storage_state, metadata=None):  # noqa: ANN001
            saved(platform, account_id, storage_state, metadata)

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager",
        _FakeSessionManager,
    )

    class _FakeContext:
        def storage_state(self, **kwargs):  # noqa: ANN003
            return {"cookies": [{"name": "a"}], "origins": []}

    target = tmp_path / "storage_state.json"
    pwcli_native.save_default_storage_state_from_context(
        {
            "platform": "tiktok",
            "account_id": "acc-1",
            "default_state_mode": "session_manager",
            "default_state_path": str(target),
        },
        _FakeContext(),
        session_metadata={
            "quality_source": "manual",
            "manual_seeded": True,
            "protected": True,
        },
    )

    saved.assert_not_called()
    assert not target.exists()


def test_save_default_storage_state_from_context_writes_raw_json(tmp_path: Path) -> None:
    """raw_json 分支保留（平台级人工导出会话的能力）。"""

    class _FakeContext:
        def storage_state(self, **kwargs):  # noqa: ANN003
            return {"cookies": [{"name": "a"}], "origins": []}

    target = tmp_path / "tiktok.json"
    pwcli_native.save_default_storage_state_from_context(
        {
            "platform": "tiktok",
            "account_id": None,
            "default_state_mode": "raw_json",
            "default_state_path": str(target),
        },
        _FakeContext(),
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["cookies"] == [{"name": "a"}]


def test_save_default_storage_state_from_context_uses_indexed_db_for_tiktok(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    class _FakeContext:
        def storage_state(self, **kwargs):  # noqa: ANN003
            observed.update(kwargs)
            return {"cookies": [{"name": "a"}], "origins": []}

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager",
        Mock(),
    )

    pwcli_native.save_default_storage_state_from_context(
        {
            "platform": "tiktok",
            "account_id": None,
            "default_state_mode": "raw_json",
            "default_state_path": str(tmp_path / "tiktok.json"),
        },
        _FakeContext(),
    )

    assert observed["indexed_db"] is True


def test_save_default_storage_state_from_context_does_not_force_indexed_db_for_non_tiktok(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    class _FakeContext:
        def storage_state(self, **kwargs):  # noqa: ANN003
            observed.update(kwargs)
            return {"cookies": [{"name": "a"}], "origins": []}

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager",
        Mock(),
    )

    pwcli_native.save_default_storage_state_from_context(
        {
            "platform": "miaoshou",
            "account_id": None,
            "default_state_mode": "raw_json",
            "default_state_path": str(tmp_path / "miaoshou.json"),
        },
        _FakeContext(),
    )

    assert "indexed_db" not in observed


def test_save_default_storage_state_from_context_supplements_tiktok_origins_from_open_pages(
    tmp_path: Path,
) -> None:
    """TikTok 的 localStorage 补充必须保留给 raw_json 分支。"""

    class _FakePage:
        def evaluate(self, script):  # noqa: ANN001
            return {
                "origin": "https://seller.tiktokshopglobalselling.com",
                "localStorage": [
                    {"name": "current_shop_region", "value": "SG"},
                    {"name": "LOCAL_IS_EFFECTIVE", "value": "1"},
                ],
                "sessionStorage": [
                    {"name": "register_libra", "value": "1"},
                ],
            }

    class _FakeContext:
        pages = [_FakePage()]

        def storage_state(self, **kwargs):  # noqa: ANN003
            return {"cookies": [{"name": "a"}], "origins": []}

    target = tmp_path / "tiktok.json"
    pwcli_native.save_default_storage_state_from_context(
        {
            "platform": "tiktok",
            "account_id": None,
            "default_state_mode": "raw_json",
            "default_state_path": str(target),
        },
        _FakeContext(),
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    origins = payload["origins"]
    assert origins[0]["origin"] == "https://seller.tiktokshopglobalselling.com"
    assert origins[0]["localStorage"] == [
        {"name": "current_shop_region", "value": "SG"},
        {"name": "LOCAL_IS_EFFECTIVE", "value": "1"},
    ]


def test_pwcli_native_no_longer_exposes_state_save_command() -> None:
    """``pwcli state-save`` 已删除（登录态由 profile 承载）。"""
    source = Path("modules/utils/pwcli_native.py").read_text(encoding="utf-8")

    assert "def command_state_save" not in source
    assert "state-save" not in source
    assert "state-load" in source


def test_launch_browser_passes_proxy_server_to_chromium(monkeypatch, tmp_path: Path) -> None:
    """代理 5 环的第 4 环：Chromium 必须带 ``--proxy-server=``。"""
    captured: dict[str, object] = {}

    class _FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):  # noqa: ANN001
        captured["command"] = list(command)
        return _FakeProcess()

    class _FakePage:
        def goto(self, *args, **kwargs):  # noqa: ANN002
            return None

    class _FakeContext:
        def __init__(self) -> None:
            self.pages: list[_FakePage] = []

        def new_page(self) -> _FakePage:
            page = _FakePage()
            self.pages.append(page)
            return page

    class _FakeBrowser:
        contexts = [_FakeContext()]

    class _FakePlaywright:
        def stop(self) -> None:
            return None

    monkeypatch.setattr(pwcli_native, "ensure_dirs", lambda: None)
    monkeypatch.setattr(pwcli_native, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(pwcli_native, "bundled_chromium_path", lambda: "chrome.exe")
    monkeypatch.setattr(pwcli_native, "wait_for_debug_port", lambda port, timeout_seconds=20.0: None)
    monkeypatch.setattr(pwcli_native, "install_console_buffer", lambda context, page: None)
    monkeypatch.setattr(pwcli_native.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        pwcli_native,
        "connect_browser",
        lambda metadata: (_FakePlaywright(), _FakeBrowser()),
    )

    pwcli_native.launch_browser(
        "shopee-acc-inspect",
        None,
        True,
        tmp_path / "profile",
        account_id="acc-1",
        proxy_server="http://10.0.0.9:8080",
    )

    command = captured["command"]
    assert "--proxy-server=http://10.0.0.9:8080" in command


def test_close_browser_gracefully_closes_via_cdp_before_stopping_playwright(monkeypatch) -> None:
    """优雅关闭：先 CDP ``Browser.close``，再 ``playwright.stop()``（顺序不能反）。"""
    calls: list[str] = []

    class _FakeCdp:
        def send(self, method, params=None):  # noqa: ANN001
            calls.append(method)

        def detach(self) -> None:
            calls.append("detach")

    class _FakeBrowser:
        def new_browser_cdp_session(self) -> _FakeCdp:
            return _FakeCdp()

    class _FakePlaywright:
        def stop(self) -> None:
            calls.append("playwright.stop")

    monkeypatch.setattr(
        pwcli_native,
        "connect_browser",
        lambda metadata: (_FakePlaywright(), _FakeBrowser()),
    )
    monkeypatch.setattr(pwcli_native, "is_process_alive", lambda pid: False)

    closed = pwcli_native.close_browser_gracefully({"pid": 1234, "port": 5555})

    assert closed is True
    assert "Browser.close" in calls
    assert "playwright.stop" in calls
    assert calls.index("Browser.close") < calls.index("playwright.stop")


def test_close_browser_gracefully_falls_back_to_taskkill(monkeypatch) -> None:
    """超时仍未退出才回落强杀。"""
    killed: list[int] = []

    class _FakeCdp:
        def send(self, method, params=None):  # noqa: ANN001
            return None

        def detach(self) -> None:
            return None

    class _FakeBrowser:
        def new_browser_cdp_session(self) -> _FakeCdp:
            return _FakeCdp()

    class _FakePlaywright:
        def stop(self) -> None:
            return None

    monkeypatch.setattr(
        pwcli_native,
        "connect_browser",
        lambda metadata: (_FakePlaywright(), _FakeBrowser()),
    )
    monkeypatch.setattr(pwcli_native, "is_process_alive", lambda pid: True)
    monkeypatch.setattr(pwcli_native, "kill_process", lambda pid: killed.append(pid))

    closed = pwcli_native.close_browser_gracefully(
        {"pid": 1234, "port": 5555},
        timeout_seconds=0,
    )

    assert closed is False
    assert killed == [1234]
