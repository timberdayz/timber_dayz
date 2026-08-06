from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from scripts.local_console_processes import (
    INSPECTION_PANEL,
    LOCAL_COLLECTION,
    LocalProcessSupervisor,
    ProcessOwnershipError,
    build_service_specs,
    decode_output_line,
)


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


def test_service_specs_use_only_the_two_approved_commands(tmp_path: Path):
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
    assert specs[INSPECTION_PANEL].command == (
        "python-test",
        "-u",
        str(tmp_path / "scripts" / "pwcli_inspection_panel.py"),
        "--no-browser",
    )


def test_process_output_decodes_utf8_and_windows_fallback_bytes():
    assert decode_output_line("迁移完成".encode("utf-8")) == "迁移完成"
    assert decode_output_line("迁移完成".encode("gb18030")) == "迁移完成"


def test_terminal_and_log_output_redact_sensitive_values(tmp_path: Path, runtime: FakeRuntime):
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


def test_start_is_idempotent_for_a_managed_process(supervisor: LocalProcessSupervisor, runtime: FakeRuntime):
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


def test_supervisor_recovers_a_valid_managed_process(tmp_path: Path, runtime: FakeRuntime):
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


def test_external_process_is_reported_but_cannot_be_stopped(tmp_path: Path, runtime: FakeRuntime):
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
