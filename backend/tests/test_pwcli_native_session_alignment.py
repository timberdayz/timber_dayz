from __future__ import annotations

from pathlib import Path

from modules.utils import pwcli_native


def test_resolve_session_platform_uses_session_prefix() -> None:
    assert pwcli_native.resolve_session_platform("tiktok-explore") == "tiktok"
    assert pwcli_native.resolve_session_platform("shopee-products-export") == "shopee"
    assert pwcli_native.resolve_session_platform("custom-debug") is None


def test_resolve_default_profile_dir_uses_platform_profile_root_without_account_id() -> None:
    path = pwcli_native.resolve_default_profile_dir("tiktok-explore", None)

    assert path == Path("F:/Vscode/python_programme/AI_code/xihong_erp/output/playwright/profiles/tiktok")


def test_resolve_default_profile_dir_uses_runtime_account_profile_with_account_id() -> None:
    path = pwcli_native.resolve_default_profile_dir("tiktok-explore", "Tiktok 2店")

    assert path == Path("F:/Vscode/python_programme/AI_code/xihong_erp/profiles/tiktok/Tiktok2店")


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
    url, headed, profile_dir, account_id = pwcli_native.parse_open_args(
        ["https://seller.tiktokglobalshop.com/", "--headed", "--account-id", "Tiktok 2店"]
    )

    assert url == "https://seller.tiktokglobalshop.com/"
    assert headed is True
    assert profile_dir is None
    assert account_id == "Tiktok 2店"


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


def test_resolve_default_state_config_is_repo_root_anchored_even_when_cwd_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo_root.mkdir()
    elsewhere.mkdir()
    monkeypatch.setattr(pwcli_native, "REPO_ROOT", repo_root)
    monkeypatch.chdir(elsewhere)

    metadata = pwcli_native.resolve_default_state_config("tiktok-explore", "Tiktok 2店")

    assert metadata["default_state_path"] == str(
        repo_root / "data" / "sessions" / "tiktok" / "Tiktok 2店" / "storage_state.json"
    )


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
