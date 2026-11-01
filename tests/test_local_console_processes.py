from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from scripts.local_console_processes import (
    INSPECTION_PANEL,
    LOCAL_COLLECTION,
    READY_URLS,
    LocalProcessSupervisor,
    ProcessOwnershipError,
    build_service_specs,
    decode_output_line,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeProcess:
    def __init__(
        self,
        pid: int,
        command: list[str],
        *,
        create_time: float = 100.0,
        output: str = "",
        running: bool = True,
    ) -> None:
        self.pid = pid
        self.command = command
        self._create_time = create_time
        self.stdout = io.StringIO(output)
        self.returncode = None if running else 1
        self.terminated = False
        self.killed = False
        self.children_terminated = False

    def poll(self):
        return self.returncode

    def create_time(self) -> float:
        return self._create_time

    def cmdline(self) -> list[str]:
        return self.command

    def is_running(self) -> bool:
        return self.returncode is None

    def children(self, recursive: bool = False):
        owner = self

        class Child:
            def terminate(self) -> None:
                owner.children_terminated = True

            def kill(self) -> None:
                owner.children_terminated = True

        return [Child()] if recursive else []

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class FakeRuntime:
    def __init__(self) -> None:
        self.started: list[FakeProcess] = []
        self.by_pid: dict[int, FakeProcess] = {}
        self.next_pid = 4000

    def popen(self, command: list[str], **_kwargs) -> FakeProcess:
        process = FakeProcess(self.next_pid, command)
        self.next_pid += 1
        self.started.append(process)
        self.by_pid[process.pid] = process
        return process

    def resolve(self, pid: int) -> FakeProcess:
        if pid not in self.by_pid:
            raise LookupError(pid)
        return self.by_pid[pid]

    def iter_processes(self):
        return list(self.by_pid.values())


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def supervisor(tmp_path: Path, runtime: FakeRuntime) -> LocalProcessSupervisor:
    return LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )


def test_local_collection_console_uses_the_development_startup_wrapper(tmp_path: Path):
    specs = build_service_specs(tmp_path, python_executable="python-test")

    assert set(specs) == {LOCAL_COLLECTION, INSPECTION_PANEL}
    assert specs[LOCAL_COLLECTION].command[:5] == (
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    )
    assert "OutputEncoding" in specs[LOCAL_COLLECTION].command[5]
    assert "start_collection_formal.ps1" in specs[LOCAL_COLLECTION].command[5]
    assert "start_local_collection_mode.ps1" not in specs[LOCAL_COLLECTION].command[5]
    assert specs[INSPECTION_PANEL].command == (
        "python-test",
        "-u",
        str(tmp_path / "scripts" / "pwcli_inspection_panel.py"),
        "--no-browser",
    )


def test_process_output_decodes_utf8_and_windows_fallback_bytes():
    assert decode_output_line("迁移完成".encode("utf-8")) == "迁移完成"
    assert decode_output_line("迁移完成".encode("gb18030")) == "迁移完成"


def test_terminal_and_log_output_redact_sensitive_values(
    tmp_path: Path, runtime: FakeRuntime
):
    terminal_lines: list[str] = []
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
        output_sink=terminal_lines.append,
    )
    process = FakeProcess(5000, ["powershell"])
    log_path = tmp_path / "logs" / "local-collection.log"
    log_path.parent.mkdir()

    supervisor._consume_output(
        LOCAL_COLLECTION,
        process,
        io.BytesIO("迁移完成 token=abc123".encode("gb18030")),
        log_path,
    )

    text = log_path.read_text(encoding="utf-8") + "\n".join(terminal_lines)
    assert "迁移完成" in text
    assert "abc123" not in text
    assert "token=<redacted>" in text


def test_collection_protocol_markers_propagate_failure_details_without_overwriting_exit_code(
    tmp_path: Path, runtime: FakeRuntime
):
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )
    started = supervisor.start(LOCAL_COLLECTION)
    process = runtime.by_pid[started["pid"]]
    log_path = tmp_path / "logs" / "local-collection.log"

    supervisor._consume_output(
        LOCAL_COLLECTION,
        process,
        io.BytesIO(
            b"XIHONG_STAGE=migration_preflight:started\n"
            b"XIHONG_FAILURE_CODE=migration_schema_drift\n"
            b"XIHONG_FAILURE_SUMMARY=schema fingerprint mismatch token=hidden\n"
            b"XIHONG_RECOVERY_HINT=manual_schema_review\n"
            b"XIHONG_SOURCE_EXIT_CODE=2\n"
            b"XIHONG_ACTUAL_FINGERPRINT=actual-fingerprint\n"
            b"XIHONG_APPROVED_FINGERPRINT=approved-fingerprint\n"
        ),
        log_path,
    )
    process.returncode = 2

    status = supervisor.status(LOCAL_COLLECTION)

    assert status["failure_code"] == "migration_schema_drift"
    assert status["source_exit_code"] == 2
    assert status["wrapper_exit_code"] == 2
    assert (
        status["last_failure_summary"] == "schema fingerprint mismatch token=<redacted>"
    )
    assert status["recovery_hint"] == "manual_schema_review"
    assert status["actual_fingerprint"] == "actual-fingerprint"
    assert status["approved_fingerprint"] == "approved-fingerprint"
    assert status["launch_stage"] == "migration_preflight:started"
    assert "hidden" not in "\n".join(
        supervisor.read_log(LOCAL_COLLECTION, max_lines=10)
    )


def test_start_is_idempotent_for_a_managed_process(
    supervisor: LocalProcessSupervisor, runtime: FakeRuntime
):
    first = supervisor.start(LOCAL_COLLECTION)
    second = supervisor.start(LOCAL_COLLECTION)

    assert first["state"] == "starting"
    assert second["pid"] == first["pid"]
    assert len(runtime.started) == 1


def test_stop_rejects_pid_reuse_when_create_time_changed(
    supervisor: LocalProcessSupervisor, runtime: FakeRuntime
):
    started = supervisor.start(LOCAL_COLLECTION)
    runtime.by_pid[started["pid"]]._create_time += 1

    with pytest.raises(ProcessOwnershipError):
        supervisor.stop(LOCAL_COLLECTION)

    assert runtime.by_pid[started["pid"]].terminated is False


def test_collection_stop_terminates_the_validated_process_tree(
    supervisor: LocalProcessSupervisor, runtime: FakeRuntime
):
    started = supervisor.start(LOCAL_COLLECTION)

    result = supervisor.stop(LOCAL_COLLECTION)

    process = runtime.by_pid[started["pid"]]
    assert result["state"] == "stopped"
    assert process.terminated is True
    assert process.children_terminated is True


def test_inspection_panel_stop_does_not_terminate_platform_browser_children(
    supervisor: LocalProcessSupervisor, runtime: FakeRuntime
):
    started = supervisor.start(INSPECTION_PANEL)

    supervisor.stop(INSPECTION_PANEL)

    process = runtime.by_pid[started["pid"]]
    assert process.terminated is True
    assert process.children_terminated is False


def test_supervisor_recovers_a_valid_managed_process(
    tmp_path: Path, runtime: FakeRuntime
):
    specs = build_service_specs(tmp_path, python_executable="python-test")
    command = list(specs[LOCAL_COLLECTION].command)
    process = FakeProcess(4567, command, create_time=77.0)
    runtime.by_pid[process.pid] = process
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "services": {
                    LOCAL_COLLECTION: {
                        "pid": process.pid,
                        "create_time": process.create_time(),
                        "launch_url": "http://localhost:5173",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    recovered = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=state_path,
        log_dir=tmp_path / "logs",
        python_executable="python-test",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda service: service == LOCAL_COLLECTION,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )

    status = recovered.status(LOCAL_COLLECTION)
    assert status["state"] == "running"
    assert status["managed"] is True
    assert status["launch_url"] == "http://localhost:5173"


def test_external_process_is_reported_but_cannot_be_stopped(
    tmp_path: Path, runtime: FakeRuntime
):
    specs = build_service_specs(tmp_path, python_executable="python-test")
    external = FakeProcess(4999, list(specs[INSPECTION_PANEL].command))
    runtime.by_pid[external.pid] = external
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        python_executable="python-test",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )

    assert supervisor.status(INSPECTION_PANEL)["state"] == "external-running"
    with pytest.raises(ProcessOwnershipError):
        supervisor.stop(INSPECTION_PANEL)


def test_startup_timeout_stops_owned_process_and_keeps_failure_visible(
    tmp_path: Path, runtime: FakeRuntime
):
    now = [10.0]
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
        time_provider=lambda: now[0],
        startup_timeout_seconds=20,
    )
    started = supervisor.start(LOCAL_COLLECTION)
    now[0] = 31.0

    first = supervisor.status(LOCAL_COLLECTION)
    second = supervisor.status(LOCAL_COLLECTION)

    assert runtime.by_pid[started["pid"]].terminated is True
    assert first["state"] == "failed"
    assert second["state"] == "failed"
    assert "启动超时" in first["last_error"]


def test_early_process_exit_failure_persists_until_the_next_start(
    supervisor: LocalProcessSupervisor, runtime: FakeRuntime
):
    started = supervisor.start(LOCAL_COLLECTION)
    runtime.by_pid[started["pid"]].returncode = 7

    first = supervisor.status(LOCAL_COLLECTION)
    second = supervisor.status(LOCAL_COLLECTION)

    assert first["state"] == "failed"
    assert second["state"] == "failed"
    assert "退出码 7" in first["last_error"]


def test_running_service_records_the_most_recent_success_timestamp(
    tmp_path: Path, runtime: FakeRuntime
):
    now = [100.0]
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda service: service == LOCAL_COLLECTION,
        wait_for_processes=lambda _processes, _timeout: ([], []),
        time_provider=lambda: now[0],
    )

    supervisor.start(LOCAL_COLLECTION)
    now[0] = 101.0

    assert supervisor.status(LOCAL_COLLECTION)["last_success_at"] == 101.0
    now[0] = 102.0
    assert supervisor.status(LOCAL_COLLECTION)["last_success_at"] == 101.0


def test_diagnostic_summary_is_not_replaced_by_generic_wrapper_exit_message(
    tmp_path: Path, runtime: FakeRuntime
):
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )
    started = supervisor.start(LOCAL_COLLECTION)
    process = runtime.by_pid[started["pid"]]
    process.returncode = 2

    supervisor._consume_output(
        LOCAL_COLLECTION,
        process,
        io.BytesIO(b"XIHONG_FAILURE_SUMMARY=approved schema fingerprint mismatch\n"),
        tmp_path / "logs" / "local-collection.log",
    )

    assert supervisor.status(LOCAL_COLLECTION)["last_failure_summary"] == (
        "approved schema fingerprint mismatch"
    )
    assert supervisor.status(LOCAL_COLLECTION)["last_error"] == (
        "approved schema fingerprint mismatch"
    )


def test_failure_protocol_creates_redacted_structured_audit_record(
    tmp_path: Path, runtime: FakeRuntime
):
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
    )
    started = supervisor.start(LOCAL_COLLECTION)
    process = runtime.by_pid[started["pid"]]

    supervisor._consume_output(
        LOCAL_COLLECTION,
        process,
        io.BytesIO(
            b"XIHONG_FAILURE_CODE=migration_schema_drift\n"
            b"XIHONG_FAILURE_SUMMARY=drift token=private-value\n"
            b"XIHONG_RECOVERY_HINT=manual_schema_review\n"
            b"XIHONG_ACTUAL_FINGERPRINT=actual-fingerprint\n"
            b"XIHONG_APPROVED_FINGERPRINT=approved-fingerprint\n"
        ),
        tmp_path / "logs" / "local-collection.log",
    )

    audit = (tmp_path / "logs" / "startup-audit.jsonl").read_text(encoding="utf-8")
    assert '"failure_code": "migration_schema_drift"' in audit
    assert "private-value" not in audit
    assert "token=<redacted>" in audit
    assert '"actual_fingerprint": "actual-fingerprint"' in audit
    assert '"approved_fingerprint": "approved-fingerprint"' in audit


def test_transient_readiness_failure_never_downgrades_a_running_service(
    tmp_path: Path, runtime: FakeRuntime
):
    """[*] 已经跑起来的系统，不许因为一次瞬时探测失败就被降级或被杀。"""
    now = [100.0]
    probe = {"value": True}
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: probe["value"],
        wait_for_processes=lambda _processes, _timeout: ([], []),
        time_provider=lambda: now[0],
        startup_timeout_seconds=20,
    )
    started = supervisor.start(LOCAL_COLLECTION)
    process = runtime.by_pid[started["pid"]]

    now[0] = 101.0
    assert supervisor.status(LOCAL_COLLECTION)["state"] == "running"

    # 一次瞬时失败；此时"启动预算"早就超了，但服务已经就绪过
    probe["value"] = False
    now[0] = 500.0
    status = supervisor.status(LOCAL_COLLECTION)

    assert status["state"] == "running"
    assert process.terminated is False
    assert process.killed is False


def test_repeated_readiness_failures_enter_observation_state_without_killing(
    tmp_path: Path, runtime: FakeRuntime
):
    """[*] 连续失败达阈值才进入观察态，并重置预算窗口——但绝不杀进程。"""
    now = [100.0]
    probe = {"value": True}
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: probe["value"],
        wait_for_processes=lambda _processes, _timeout: ([], []),
        time_provider=lambda: now[0],
        startup_timeout_seconds=20,
        readiness_failure_threshold=3,
    )
    started = supervisor.start(LOCAL_COLLECTION)
    process = runtime.by_pid[started["pid"]]

    now[0] = 101.0
    assert supervisor.status(LOCAL_COLLECTION)["state"] == "running"

    probe["value"] = False
    now[0] = 102.0
    assert supervisor.status(LOCAL_COLLECTION)["state"] == "running"
    assert supervisor.status(LOCAL_COLLECTION)["state"] == "running"
    # 第三次连续失败：进入观察态，但进程还活着
    assert supervisor.status(LOCAL_COLLECTION)["state"] == "starting"
    assert process.terminated is False
    assert process.killed is False


def test_startup_timeout_records_structured_audit_evidence(
    tmp_path: Path, runtime: FakeRuntime
):
    """[*] 真正启动失败时，必须留下 startup-audit 证据。"""
    now = [10.0]
    supervisor = LocalProcessSupervisor(
        repo_root=tmp_path,
        state_path=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        popen_factory=runtime.popen,
        process_resolver=runtime.resolve,
        process_iterator=runtime.iter_processes,
        readiness_probe=lambda _service: False,
        wait_for_processes=lambda _processes, _timeout: ([], []),
        time_provider=lambda: now[0],
        startup_timeout_seconds=20,
    )
    supervisor.start(LOCAL_COLLECTION)
    now[0] = 31.0

    status = supervisor.status(LOCAL_COLLECTION)

    assert status["state"] == "failed"
    audit = (tmp_path / "logs" / "startup-audit.jsonl").read_text(encoding="utf-8")
    assert '"failure_code": "startup_timeout"' in audit


def test_console_probe_covers_every_run_py_backend_port_fallback(monkeypatch):
    """[*] 控制台探针必须覆盖 run.py 的全部端口回退，否则会误杀健康的后端。"""
    spec = importlib.util.spec_from_file_location(
        "run_module_for_console_tests", PROJECT_ROOT / "run.py"
    )
    run_module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(run_module)

    probe_ports = {url.split(":")[2].split("/")[0] for url in READY_URLS}
    monkeypatch.setattr(run_module, "_is_port_in_use", lambda port: False)

    chosen_ports = []
    for candidate in (8001, 18001, 18011, 18021, 18031, 18041):
        monkeypatch.setattr(
            run_module,
            "_can_bind_local_port",
            lambda port, host="127.0.0.1": port == candidate,
        )
        chosen = run_module._choose_local_backend_port(8001)
        assert chosen is not None
        chosen_ports.append(str(chosen))

    assert set(chosen_ports) <= probe_ports
