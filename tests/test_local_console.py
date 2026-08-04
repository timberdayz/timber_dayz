from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scripts.local_console import (
    TOKEN_HEADER,
    build_app,
    open_existing_controller,
    write_controller_state,
)
from scripts.local_console_processes import ProcessOwnershipError


class FakeSupervisor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.fail_stop = False

    def all_statuses(self):
        return [
            {
                "id": "local-collection",
                "label": "本地采集系统",
                "description": "数据采集、云端同步与本地测试",
                "state": "stopped",
                "managed": False,
                "pid": None,
                "launch_url": None,
                "last_error": None,
                "log_available": False,
            }
        ]

    def start(self, service_id: str):
        self.calls.append(("start", service_id))
        return {"id": service_id, "state": "starting"}

    def stop(self, service_id: str):
        self.calls.append(("stop", service_id))
        if self.fail_stop:
            raise ProcessOwnershipError("进程身份不匹配；secret=do-not-return")
        return {"id": service_id, "state": "stopped"}

    def open(self, service_id: str):
        self.calls.append(("open", service_id))
        return {"id": service_id, "state": "running"}

    def stop_all(self):
        self.calls.append(("stop-all", None))
        return [{"id": "local-collection", "state": "stopped"}]

    def read_log(self, service_id: str):
        self.calls.append(("log", service_id))
        return [
            "token=abc123 password=hunter2",
            "postgresql://erp_user:db-secret@127.0.0.1:5432/xihong",
            "normal status line",
        ]


def _client(tmp_path: Path, supervisor: FakeSupervisor) -> TestClient:
    index_path = tmp_path / "index.html"
    index_path.write_text("<h1>西虹 ERP 本地控制台</h1>", encoding="utf-8")
    return TestClient(
        build_app(supervisor=supervisor, token="correct-token", index_path=index_path)
    )


def _headers(token: str = "correct-token") -> dict[str, str]:
    return {TOKEN_HEADER: token}


def test_api_rejects_missing_or_incorrect_token(tmp_path: Path):
    client = _client(tmp_path, FakeSupervisor())

    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers=_headers("wrong")).status_code == 401
    assert client.get("/api/status", headers=_headers()).status_code == 200


def test_security_headers_are_added_to_html_and_api_responses(tmp_path: Path):
    client = _client(tmp_path, FakeSupervisor())

    for response in [client.get("/"), client.get("/api/status", headers=_headers())]:
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'self'" in response.headers["content-security-policy"]


def test_fixed_service_routes_delegate_without_accepting_commands(tmp_path: Path):
    supervisor = FakeSupervisor()
    client = _client(tmp_path, supervisor)

    assert client.post(
        "/api/services/local-collection/start", headers=_headers()
    ).status_code == 200
    assert client.post(
        "/api/services/local-collection/open", headers=_headers()
    ).status_code == 200
    assert client.post(
        "/api/services/local-collection/stop", headers=_headers()
    ).status_code == 200
    assert client.post(
        "/api/services/inspection-panel/start", headers=_headers()
    ).status_code == 200
    assert client.post(
        "/api/services/inspection-panel/open", headers=_headers()
    ).status_code == 200
    assert client.post(
        "/api/services/inspection-panel/stop", headers=_headers()
    ).status_code == 200
    assert client.post("/api/services/stop-all", headers=_headers()).status_code == 200

    assert supervisor.calls == [
        ("start", "local-collection"),
        ("open", "local-collection"),
        ("stop", "local-collection"),
        ("start", "inspection-panel"),
        ("open", "inspection-panel"),
        ("stop", "inspection-panel"),
        ("stop-all", None),
    ]
    assert client.post(
        "/api/services/arbitrary/start",
        headers=_headers(),
        json={"command": "Remove-Item -Recurse C:\\"},
    ).status_code == 404


def test_ownership_error_is_sanitized_and_returned_as_conflict(tmp_path: Path):
    supervisor = FakeSupervisor()
    supervisor.fail_stop = True
    client = _client(tmp_path, supervisor)

    response = client.post(
        "/api/services/local-collection/stop", headers=_headers()
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "该进程不受本控制台管理，操作已拒绝"}
    assert "do-not-return" not in response.text


def test_log_route_redacts_credentials_and_tokens(tmp_path: Path):
    supervisor = FakeSupervisor()
    client = _client(tmp_path, supervisor)

    response = client.get(
        "/api/services/local-collection/log", headers=_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lines"][-1] == "normal status line"
    assert "abc123" not in response.text
    assert "hunter2" not in response.text
    assert "db-secret" not in response.text
    assert response.text.count("<redacted>") >= 3


class FakeControllerProcess:
    def __init__(self, create_time: float, command: list[str]) -> None:
        self._create_time = create_time
        self._command = command

    def is_running(self) -> bool:
        return True

    def create_time(self) -> float:
        return self._create_time

    def cmdline(self) -> list[str]:
        return self._command


def test_existing_controller_is_validated_and_reopened(tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        """{
          "controller": {
            "pid": 321,
            "create_time": 55.5,
            "port": 8742,
            "token": "saved-token"
          }
        }""",
        encoding="utf-8",
    )
    opened: list[str] = []
    probes: list[tuple[str, str]] = []

    result = open_existing_controller(
        state_path,
        process_resolver=lambda _pid: FakeControllerProcess(
            55.5, ["pythonw", "scripts/local_console.py"]
        ),
        readiness_probe=lambda url, token: probes.append((url, token)) or True,
        url_opener=opened.append,
    )

    assert result is True
    assert probes == [("http://127.0.0.1:8742/api/status", "saved-token")]
    assert opened == ["http://127.0.0.1:8742/?token=saved-token"]


def test_existing_controller_rejects_reused_pid_without_opening(tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        """{
          "controller": {
            "pid": 321,
            "create_time": 55.5,
            "port": 8742,
            "token": "stale-token"
          }
        }""",
        encoding="utf-8",
    )
    opened: list[str] = []

    result = open_existing_controller(
        state_path,
        process_resolver=lambda _pid: FakeControllerProcess(
            99.0, ["pythonw", "scripts/local_console.py"]
        ),
        readiness_probe=lambda _url, _token: True,
        url_opener=opened.append,
    )

    assert result is False
    assert opened == []


def test_writing_controller_state_preserves_service_records(tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"services":{"local-collection":{"pid":123}}}', encoding="utf-8"
    )

    write_controller_state(
        state_path,
        pid=999,
        create_time=88.0,
        port=8740,
        token="new-token",
    )

    content = state_path.read_text(encoding="utf-8")
    assert '"local-collection"' in content
    assert '"create_time": 88.0' in content
    assert '"new-token"' in content


def test_root_launcher_starts_the_local_console_from_the_repository_root():
    launcher = Path("local_console.cmd").read_text(encoding="ascii")

    assert 'cd /d "%~dp0"' in launcher
    assert "scripts\\local_console.py" in launcher
    assert "pythonw.exe" in launcher
    assert "start_collection_formal.ps1" not in launcher
    assert "pwcli_inspection_panel.py" not in launcher


def test_static_console_has_the_approved_content_and_token_handling():
    static_dir = Path("scripts/local_console_static")
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    script = (static_dir / "app.js").read_text(encoding="utf-8")
    styles = (static_dir / "styles.css").read_text(encoding="utf-8")
    combined = "\n".join([html, script])

    for text in [
        "西虹 ERP 本地控制台",
        "本地采集系统",
        "数据采集、云端同步与本地测试",
        "巡店与会话",
        "人工巡店并保存平台登录会话",
        "启动",
        "打开系统",
        "启动面板",
        "打开面板",
        "停止",
        "停止全部",
        "未运行",
        "启动中",
        "运行中",
        "停止中",
        "启动失败",
        "外部运行",
    ]:
        assert text in combined

    assert 'history.replaceState({}, document.title, window.location.pathname)' in script
    assert "X-Local-Console-Token" in script
    assert ".textContent" in script
    assert ".innerHTML" not in script
    assert "@media" in styles
    assert "border-radius: 8px" in styles


def test_service_action_does_not_override_the_state_rendered_button_lock():
    script = Path("scripts/local_console_static/app.js").read_text(encoding="utf-8")
    action_function = script.split("async function runServiceAction", 1)[1].split(
        "async function showLog", 1
    )[0]

    assert "button.disabled = false" not in action_function
