from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("powershell") is None, reason="requires Windows PowerShell")
def test_formal_launcher_preserves_stderr_migration_protocol_and_exit_code(tmp_path: Path):
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


@pytest.mark.skipif(shutil.which("powershell") is None, reason="requires Windows PowerShell")
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
