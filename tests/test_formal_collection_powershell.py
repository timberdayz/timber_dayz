from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
def test_formal_launcher_preserves_stderr_migration_protocol_and_exit_code(
    tmp_path: Path,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python.cmd"
    fake_python.write_text(
        "@echo off\n"
        "echo XIHONG_FAILURE_CODE=migration_schema_drift 1>&2\n"
        "echo XIHONG_FAILURE_SUMMARY=schema fingerprint is not approved 1>&2\n"
        "echo XIHONG_RECOVERY_HINT=manual_schema_review 1>&2\n"
        "echo XIHONG_SOURCE_EXIT_CODE=2 1>&2\n"
        "echo XIHONG_ACTUAL_FINGERPRINT=actual-fingerprint 1>&2\n"
        "echo XIHONG_APPROVED_FINGERPRINT=approved-fingerprint 1>&2\n"
        "exit /b 2\n",
        encoding="ascii",
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "start_collection_formal.ps1"),
            "-SkipTunnel",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 2, output
    assert "XIHONG_FAILURE_CODE=migration_schema_drift" in output
    assert "XIHONG_FAILURE_SUMMARY=schema fingerprint is not approved" in output
    assert "XIHONG_RECOVERY_HINT=manual_schema_review" in output
    assert "XIHONG_SOURCE_EXIT_CODE=2" in output
    assert "XIHONG_ACTUAL_FINGERPRINT=actual-fingerprint" in output
    assert "XIHONG_APPROVED_FINGERPRINT=approved-fingerprint" in output
    assert "XIHONG_STAGE=migration_write:failed" in output


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
def test_formal_launcher_uses_process_exit_code_when_stderr_source_exit_code_is_invalid(
    tmp_path: Path,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python.cmd"
    fake_python.write_text(
        "@echo off\n"
        "echo XIHONG_FAILURE_CODE=migration_schema_drift 1>&2\n"
        "echo XIHONG_FAILURE_SUMMARY=schema fingerprint is not approved 1>&2\n"
        "echo XIHONG_RECOVERY_HINT=manual_schema_review 1>&2\n"
        "echo XIHONG_SOURCE_EXIT_CODE=not-an-integer 1>&2\n"
        "exit /b 2\n",
        encoding="ascii",
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "start_collection_formal.ps1"),
            "-SkipTunnel",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 2, output
    assert "XIHONG_FAILURE_CODE=migration_schema_drift" in output
    assert "XIHONG_SOURCE_EXIT_CODE=2" in output
    assert "XIHONG_STAGE=migration_write:failed" in output


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
def test_formal_launcher_preserves_backend_schema_failure_protocol(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python.cmd"
    fake_python.write_text(
        "@echo off\n"
        'echo %* | findstr /c:"run_current_schema_migrations.py" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        'echo %* | findstr /c:"check_local_run_env.py" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        'echo %* | findstr /c:"run.py" >nul\n'
        "if not errorlevel 1 (\n"
        "  echo XIHONG_FAILURE_CODE=schema_incomplete 1>&2\n"
        "  echo XIHONG_FAILURE_SUMMARY=missing a_class.payroll_manual_inputs 1>&2\n"
        "  echo XIHONG_RECOVERY_HINT=run protected current-schema migration 1>&2\n"
        "  echo XIHONG_SOURCE_EXIT_CODE=1 1>&2\n"
        "  exit /b 1\n"
        ")\n"
        "exit /b 0\n",
        encoding="ascii",
    )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "start_collection_formal.ps1"),
            "-SkipTunnel",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "XIHONG_FAILURE_CODE=schema_incomplete" in output
    assert "missing a_class.payroll_manual_inputs" in output
    assert "XIHONG_FAILURE_CODE=backend_start_failed" not in output


CONFLICT_CONTAINERS = (
    "xihong_erp_backend_api",
    "xihong_erp_backend_collector",
    "xihong_erp_celery_worker",
    "xihong_erp_celery_beat",
)


def _write_fake_docker(fake_bin: Path, docker_log: Path, *, failing: bool) -> None:
    """假 docker：记录每次调用；failing=True 时模拟"容器不存在"的真实行为。"""
    log_path = str(docker_log)
    body = "@echo off\r\n" f'echo %* >> "{log_path}"\r\n'
    if failing:
        body += (
            "echo Error: No such container: xihong_erp_celery_beat 1>&2\r\n"
            "exit /b 1\r\n"
        )
    else:
        body += "exit /b 0\r\n"
    (fake_bin / "docker.cmd").write_text(body, encoding="ascii")


def _run_launcher(
    tmp_path: Path, script_name: str, *, failing_docker: bool
) -> tuple[int, str, list[str]]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    docker_log = tmp_path / "docker.log"
    _write_fake_docker(fake_bin, docker_log, failing=failing_docker)
    (fake_bin / "python.cmd").write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")

    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    arguments = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / script_name),
    ]
    if script_name == "start_collection_formal.ps1":
        arguments += ["-SkipTunnel", "-SkipChecks"]

    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    lines: list[str] = []
    if docker_log.exists():
        lines = [
            line.strip()
            for line in docker_log.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if line.strip()
        ]
    return result.returncode, output, lines


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
@pytest.mark.parametrize(
    "script_name",
    ["start_collection_formal.ps1", "start_local_collection_mode.ps1"],
)
def test_launcher_stops_every_conflicting_container_individually(
    tmp_path: Path, script_name: str
):
    """docker stop 必须一个容器一次调用。

    一条 docker stop 带多个容器时，只要有一个不存在，整条就失败，
    后面的容器根本没被停 —— celery 就是这样漏掉的，于是它继续持锁，
    把迁移前的 pg_dump 备份堵死，启动被 fail-closed 拦停。
    """
    _returncode, output, lines = _run_launcher(
        tmp_path, script_name, failing_docker=False
    )

    stop_lines = [line for line in lines if line.startswith("stop ")]
    assert stop_lines, output
    stopped: list[str] = []
    for line in stop_lines:
        names = line.split()[1:]
        assert len(names) == 1, f"docker stop must target one container: {line}"
        stopped.append(names[0])

    for expected in CONFLICT_CONTAINERS:
        assert expected in stopped, f"{expected} not stopped; stopped={stopped}"


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
@pytest.mark.parametrize(
    "script_name",
    ["start_collection_formal.ps1", "start_local_collection_mode.ps1"],
)
def test_launcher_keeps_stopping_containers_after_one_is_missing(
    tmp_path: Path, script_name: str
):
    """某个容器不存在（docker 往 stderr 写 + 退出码非 0）不能打断后面的停止。"""
    _returncode, output, lines = _run_launcher(
        tmp_path, script_name, failing_docker=True
    )

    stopped = [line.split()[1] for line in lines if line.startswith("stop ")]
    for expected in CONFLICT_CONTAINERS:
        assert expected in stopped, f"{expected} not stopped; stopped={stopped}"


@pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requires Windows PowerShell"
)
def test_formal_launcher_keeps_celery_workers_out_of_the_migration_window(
    tmp_path: Path,
):
    """celery 在刷物化视图时长期持锁，启动前必须停掉。"""
    _returncode, _output, lines = _run_launcher(
        tmp_path, "start_collection_formal.ps1", failing_docker=False
    )

    stopped = [line.split()[1] for line in lines if line.startswith("stop ")]
    assert "xihong_erp_celery_worker" in stopped
    assert "xihong_erp_celery_beat" in stopped
