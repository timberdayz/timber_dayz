from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.services.main_account_session_lock import MainAccountSessionLockTimeoutError
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


def _rows_with_proxy() -> list[MainAccountRow]:
    return [
        MainAccountRow(
            "shopee",
            "hongxikeji:main",
            "hongxikeji:main",
            "",
            proxy_enabled=True,
            proxy_server="http://10.0.0.9:8080",
            proxy_username="proxy-user",
            proxy_password="proxy-pass",
        ),
    ]


class _FakeLock:
    """记录加锁/放锁的假锁（不连 Redis）。"""

    def __init__(self) -> None:
        self.acquired: list[tuple[str, str]] = []
        self.released: list[tuple[str, str]] = []

    def acquire(self, platform: str, main_account_id: str, *, timeout=None):  # noqa: ANN001
        acquired = self.acquired
        released = self.released

        class _Ctx:
            async def __aenter__(self):
                acquired.append((platform, main_account_id))
                return None

            async def __aexit__(self, *args):  # noqa: ANN002
                released.append((platform, main_account_id))
                return False

        return _Ctx()


class _BusyLock:
    """模拟「账号正在采集中」：加锁立刻超时。"""

    def acquire(self, platform: str, main_account_id: str, *, timeout=None):  # noqa: ANN001
        class _Ctx:
            async def __aenter__(self):
                raise MainAccountSessionLockTimeoutError("账号会话被其它采集任务占用")

            async def __aexit__(self, *args):  # noqa: ANN002
                return False

        return _Ctx()


def _client(state: PanelState) -> TestClient:
    return TestClient(build_app(state))


def _write_session_meta(repo_root: Path, platform: str, work_tag: str, pid: int) -> None:
    session = f"{platform}-{work_tag}"
    directory = repo_root / "output" / "playwright" / ".pwcli_native" / "sessions" / session
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "session.json").write_text(
        json.dumps({"session": session, "pid": pid, "port": 12345}),
        encoding="utf-8",
    )


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
            "work_tag": "tiktok-tiktok-1-a9983eb0-inspect",
            "status": "idle",
        },
    ]


def test_accounts_api_never_leaks_proxy_credentials():
    """代理凭据不能出现在 HTTP 响应里（面板响应会进浏览器 DOM）。"""
    client = _client(PanelState(token="secret", account_rows_loader=_rows_with_proxy))

    body = client.get("/api/accounts?token=secret").text

    assert "proxy-pass" not in body
    assert "proxy-user" not in body
    assert "10.0.0.9" not in body


def test_open_executes_only_allowlisted_helper_commands(tmp_path: Path):
    calls: list[list[str]] = []
    lock = _FakeLock()

    def command_runner(command, env=None):  # noqa: ANN001
        calls.append(command)
        return CommandResult(exit_code=0, stdout="ok", stderr="")

    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=command_runner,
        repo_root=tmp_path,
        session_lock=lock,
    )
    client = _client(state)

    open_response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert open_response.status_code == 200
    assert open_response.json()["status"] == "opened"
    joined = "\n".join(" ".join(command) for command in calls)
    assert "Open-PwcliShopee" in joined
    assert "Invoke-Expression" not in joined
    assert "Start-Process" not in joined


def test_save_endpoint_is_removed():
    """「保存会话」端点必须已删除（返回 404）。"""
    calls: list[list[str]] = []
    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command, env=None: calls.append(command) or CommandResult(0, "", ""),
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/save?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert response.status_code == 404
    assert calls == []


def test_open_takes_account_lock_before_running_command(tmp_path: Path):
    """巡店必须先拿到账号会话锁（与采集同一把锁）。"""
    calls: list[list[str]] = []
    lock = _FakeLock()

    def command_runner(command, env=None):  # noqa: ANN001
        calls.append(command)
        return CommandResult(exit_code=0, stdout="ok", stderr="")

    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=command_runner,
        repo_root=tmp_path,
        session_lock=lock,
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert response.status_code == 200
    assert lock.acquired == [("shopee", "hongxikeji:main")]


def test_open_returns_409_when_account_lock_is_busy(tmp_path: Path):
    """锁被占用时必须给明确提示 + 409（不是让 Chromium 自己报 ProcessSingleton）。"""
    calls: list[list[str]] = []

    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command, env=None: calls.append(command) or CommandResult(0, "", ""),
        repo_root=tmp_path,
        session_lock=_BusyLock(),
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert response.status_code == 409
    assert "采集中" in response.json()["detail"]
    assert calls == []


def test_open_releases_account_lock_when_browser_process_is_gone(tmp_path: Path):
    """浏览器进程消失即放锁（正常关闭 -> 刷盘 -> 再放锁）。"""
    lock = _FakeLock()
    work_tag = "shopee-hongxikeji-main-inspect"
    _write_session_meta(tmp_path, "shopee", work_tag, pid=424242)

    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command, env=None: CommandResult(0, "ok", ""),
        repo_root=tmp_path,
        session_lock=lock,
        session_poll_interval_seconds=0.05,
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )
    assert response.status_code == 200

    deadline = time.time() + 5
    while time.time() < deadline and not lock.released:
        time.sleep(0.05)

    assert lock.released == [("shopee", "hongxikeji:main")]


def test_open_forwards_account_proxy_server_and_credentials(tmp_path: Path):
    """代理 5 环的第 2 环：面板把代理地址拼进命令，凭据走环境变量。"""
    calls: list[list[str]] = []
    envs: list[dict[str, str]] = []

    def command_runner(command, env=None):  # noqa: ANN001
        calls.append(command)
        envs.append(dict(env or {}))
        return CommandResult(exit_code=0, stdout="ok", stderr="")

    state = PanelState(
        token="secret",
        account_rows_loader=_rows_with_proxy,
        command_runner=command_runner,
        repo_root=tmp_path,
        session_lock=_FakeLock(),
    )
    client = _client(state)

    response = client.post(
        "/api/accounts/open?token=secret",
        json={"platform": "shopee", "account_id": "hongxikeji:main"},
    )

    assert response.status_code == 200
    joined = " ".join(calls[0])
    assert "-ProxyServer" in joined
    assert "http://10.0.0.9:8080" in joined
    # 凭据只走环境变量，不进命令行（进程列表可见）
    assert "proxy-pass" not in joined
    assert envs[0]["PWCLI_PROXY_USERNAME"] == "proxy-user"
    assert envs[0]["PWCLI_PROXY_PASSWORD"] == "proxy-pass"


def test_unknown_account_is_rejected_without_running_command():
    calls: list[list[str]] = []
    state = PanelState(
        token="secret",
        account_rows_loader=_rows,
        command_runner=lambda command, env=None: calls.append(command) or CommandResult(0, "", ""),
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
        command_runner=lambda command, env=None: calls.append(command) or CommandResult(0, "", ""),
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


def test_static_panel_page_has_no_save_button():
    """前端不得再有「保存会话」按钮（登录态由浏览器 profile 自动保存）。"""
    html = Path("scripts/pwcli_inspection_panel_static/index.html").read_text(encoding="utf-8")

    assert "保存会话" not in html
    assert "打开巡店" in html
    assert "profile" in html

    assert "save-check" not in html
    assert "saveChecksPassed" not in html
    assert "保存前确认项未全部勾选" not in html
    assert "card.querySelector('.save').disabled" not in html
    assert "runAction('save'" not in html


def test_favicon_route_does_not_log_as_not_found():
    client = _client(PanelState(token="secret", account_rows_loader=_rows))

    response = client.get("/favicon.ico")

    assert response.status_code == 204
