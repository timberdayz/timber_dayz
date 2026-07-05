from __future__ import annotations

import socket
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.pwcli_account_inventory import MainAccountRow
from scripts.pwcli_inspection_panel import (
    CommandResult,
    PanelState,
    build_app,
    build_pwcli_action_command,
    find_available_port,
)


def _rows() -> list[MainAccountRow]:
    return [
        MainAccountRow("shopee", "hongxikeji:main", "hongxikeji:main", ""),
        MainAccountRow("tiktok", "Tiktok 1店", "Tiktok 1店", "seller@example.com"),
        MainAccountRow("legacy", "unsupported", "Legacy", ""),
    ]


def _client(state: PanelState) -> TestClient:
    return TestClient(build_app(state))


def test_api_requires_valid_token():
    client = _client(PanelState(token="secret", account_rows_loader=_rows))

    assert client.get("/api/accounts").status_code == 401
    assert client.get("/api/accounts?token=wrong").status_code == 401
    assert client.get("/api/accounts?token=secret").status_code == 200


def test_accounts_api_returns_enabled_supported_accounts_with_status():
    client = _client(PanelState(token="secret", account_rows_loader=_rows))

    response = client.get("/api/accounts?token=secret")

    assert response.status_code == 200
    assert response.json() == [
        {
            "platform": "shopee",
            "display_name": "hongxikeji:main",
            "account_id": "hongxikeji:main",
            "work_tag": "shopee-hongxikeji-main-inspect",
            "status": "idle",
        },
        {
            "platform": "tiktok",
            "display_name": "Tiktok 1店 (seller@example.com)",
            "account_id": "Tiktok 1店",
            "work_tag": "tiktok-tiktok-1-inspect",
            "status": "idle",
        },
    ]


def test_open_and_save_execute_only_allowlisted_helper_commands(tmp_path: Path):
    calls: list[list[str]] = []

    def command_runner(command: list[str]) -> CommandResult:
        calls.append(command)
        return CommandResult(exit_code=0, stdout="ok", stderr="")

    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=command_runner,
        repo_root=tmp_path,
    )
    client = _client(state)

    open_response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )
    save_response = client.post(
        "/api/accounts/save?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert open_response.status_code == 200
    assert open_response.json()["status"] == "opened"
    assert save_response.status_code == 200
    assert save_response.json()["status"] == "saved"
    joined = "\n".join(" ".join(command) for command in calls)
    assert "Open-PwcliShopee" in joined
    assert "Save-PwcliShopeeState" in joined
    assert "Invoke-Expression" not in joined
    assert "Start-Process" not in joined


def test_unknown_account_is_rejected_without_running_command():
    calls: list[list[str]] = []
    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command: calls.append(command) or CommandResult(0, "", ""),
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "missing"},
    )

    assert response.status_code == 404
    assert calls == []


def test_skip_clears_status_without_running_command():
    calls: list[list[str]] = []
    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command: calls.append(command) or CommandResult(0, "", ""),
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/skip?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert calls == []


def test_build_pwcli_action_command_quotes_account_id_and_uses_repo_helper(tmp_path: Path):
    account = {
        "platform": "tiktok",
        "account_id": "seller'oops",
        "work_tag": "tiktok-seller-oops-inspect",
    }

    command = build_pwcli_action_command("open", account, tmp_path)
    command_text = command[-1]

    assert command[:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "pwcli_helpers.ps1" in command_text
    assert "Open-PwcliTiktok" in command_text
    assert "-AccountId 'seller''oops'" in command_text
    assert "[Console]::OutputEncoding" in command_text
    assert "$OutputEncoding" in command_text


def test_run_subprocess_command_forces_utf8_decoding(monkeypatch):
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="中文 ok", stderr="")

    monkeypatch.setattr("scripts.pwcli_inspection_panel.subprocess.run", fake_run)

    result = CommandResult(exit_code=-1, stdout="", stderr="")
    from scripts.pwcli_inspection_panel import run_subprocess_command

    result = run_subprocess_command(["powershell", "-Command", "Write-Output ok"])

    assert result.exit_code == 0
    assert result.stdout == "中文 ok"
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"


def test_find_available_port_skips_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        occupied = sock.getsockname()[1]
        selected = find_available_port(occupied, occupied + 1)

    assert selected == occupied + 1


def test_static_panel_page_contains_controls_and_save_confirmations():
    html = Path("scripts/pwcli_inspection_panel_static/index.html").read_text(encoding="utf-8")

    for text in [
        "PWCLI 本地巡店面板",
        "平台筛选",
        "搜索账号",
        "打开巡店",
        "保存会话",
        "跳过/清除状态",
        "当前不是登录页",
        "当前不是验证码页",
        "当前不是报错页",
        "页面已稳定进入后台或正常业务页面",
    ]:
        assert text in html


def test_favicon_route_does_not_log_as_not_found():
    client = _client(PanelState(token="secret", account_rows_loader=_rows))

    response = client.get("/favicon.ico")

    assert response.status_code == 204
