from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts.local_migration_backup import (
    DOCKER_COMMAND_TIMEOUT_SECONDS,
    LOCK_TIMEOUT_ENV,
    BackupValidationError,
    _safe_failure_reason,
    create_and_verify_backup,
    verify_backup_metadata,
)
from scripts.run_current_schema_migrations import MigrationState


class RecordingRunner:
    def __init__(self, *, restore_exit_code: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []
        self.restore_exit_code = restore_exit_code

    def __call__(self, command: list[str], **kwargs):
        self.commands.append(command)
        self.kwargs.append(kwargs)
        if command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_bytes(b"PGDMP-test-backup")
        return type(
            "Result",
            (),
            {
                "returncode": self.restore_exit_code if "pg_restore" in command else 0,
                "stderr": "",
            },
        )()


def _state() -> MigrationState:
    return MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision="20260805_payroll_backfill_audit",
        schema_fingerprint="approved-fingerprint",
    )


def test_backup_uses_docker_custom_format_and_verifies_readability(tmp_path: Path):
    runner = RecordingRunner()

    metadata = create_and_verify_backup(
        "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        docker_runner=runner,
        now=lambda: "20260812T010203Z",
    )

    metadata_path = Path(metadata["metadata_path"])
    assert metadata_path.exists()
    assert Path(metadata["backup_path"]).suffix == ".dump"
    assert metadata["verification"] == "pg_restore_list_passed"
    assert metadata["legacy_revision"] == "20260805_payroll_backfill_audit"
    assert metadata["current_revision"] is None
    assert metadata["schema_fingerprint"] == "approved-fingerprint"
    assert "secret" not in metadata_path.read_text(encoding="utf-8")
    assert any("pg_dump" in command for command in runner.commands)
    assert any("pg_restore" in command for command in runner.commands)


def test_backup_rejects_an_unreadable_restore_archive(tmp_path: Path):
    with pytest.raises(BackupValidationError, match="pg_restore --list failed"):
        create_and_verify_backup(
            "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
            _state(),
            backup_directory=tmp_path,
            docker_runner=RecordingRunner(restore_exit_code=1),
            now=lambda: "20260812T010203Z",
        )


def test_backup_decodes_docker_output_as_utf8_with_replacement(tmp_path: Path):
    runner = RecordingRunner()

    create_and_verify_backup(
        "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        docker_runner=runner,
        now=lambda: "20260812T010203Z",
    )

    docker_kwargs = [
        kwargs
        for command, kwargs in zip(runner.commands, runner.kwargs)
        if command[0] == "docker"
    ]
    assert docker_kwargs
    assert all(kwargs["encoding"] == "utf-8" for kwargs in docker_kwargs)
    assert all(kwargs["errors"] == "replace" for kwargs in docker_kwargs)


def test_backup_metadata_rejects_changed_schema_evidence(tmp_path: Path):
    archive = tmp_path / "migration.dump"
    archive.write_bytes(b"PGDMP-test-backup")
    metadata_path = tmp_path / "migration.json"
    metadata = {
        "backup_path": str(archive),
        "backup_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "legacy_revision": "20260805_payroll_backfill_audit",
        "current_revision": None,
        "schema_fingerprint": "previous-fingerprint",
        "verification": "pg_restore_list_passed",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(
        BackupValidationError, match="schema fingerprint does not match"
    ):
        verify_backup_metadata(metadata_path, _state())


def test_backup_tool_has_a_read_only_metadata_verification_cli_contract():
    source = Path("scripts/local_migration_backup.py").read_text(encoding="utf-8")

    assert "--verify-metadata" in source
    assert "--database-url" in source
    assert 'if __name__ == "__main__"' in source


class HangingDumpRunner(RecordingRunner):
    """模拟 pg_dump 被锁住一直不返回（真实事故：长事务持锁，pg_dump 无限等）。"""

    def __call__(self, command: list[str], **kwargs):
        if "pg_dump" in command:
            self.commands.append(command)
            self.kwargs.append(kwargs)
            raise subprocess.TimeoutExpired(
                cmd=command, timeout=kwargs.get("timeout", 0)
            )
        return super().__call__(command, **kwargs)


class FailingDumpRunner(RecordingRunner):
    """模拟 pg_dump 直接失败并把连接细节写进 stderr。"""

    def __call__(self, command: list[str], **kwargs):
        if "pg_dump" in command:
            self.commands.append(command)
            self.kwargs.append(kwargs)
            return type(
                "Result",
                (),
                {
                    "returncode": 1,
                    "stderr": (
                        "pg_dump: error: connection to server at 10.11.12.13 "
                        "(10.11.12.13), port 5432 failed: password=sup3rs3cret "
                        "dbname=xihong_erp\n"
                    ),
                },
            )()
        return super().__call__(command, **kwargs)


def test_backup_pg_dump_sets_a_server_side_lock_timeout(tmp_path: Path):
    """pg_dump 必须自己带锁等待上限，不能被别的长事务无限拖住。"""
    runner = RecordingRunner()

    create_and_verify_backup(
        "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        docker_runner=runner,
        now=lambda: "20260812T010203Z",
    )

    dump_commands = [command for command in runner.commands if "pg_dump" in command]
    assert dump_commands, runner.commands
    dump_command = dump_commands[0]
    assert "-e" in dump_command
    assert LOCK_TIMEOUT_ENV in dump_command
    assert "lock_timeout=60s" in LOCK_TIMEOUT_ENV


def test_backup_docker_commands_are_all_bounded_by_a_timeout(tmp_path: Path):
    """任何 docker 调用都不能无限期挂住，否则启动流程永远卡死。"""
    runner = RecordingRunner()

    create_and_verify_backup(
        "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        docker_runner=runner,
        now=lambda: "20260812T010203Z",
    )

    docker_kwargs = [
        kwargs
        for command, kwargs in zip(runner.commands, runner.kwargs)
        if command[0] == "docker"
    ]
    assert docker_kwargs
    assert all(
        kwargs.get("timeout") == DOCKER_COMMAND_TIMEOUT_SECONDS
        for kwargs in docker_kwargs
    ), docker_kwargs


def test_backup_reports_a_hung_docker_command_as_a_validation_error(tmp_path: Path):
    with pytest.raises(BackupValidationError, match="timed out"):
        create_and_verify_backup(
            "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
            _state(),
            backup_directory=tmp_path,
            docker_runner=HangingDumpRunner(),
            now=lambda: "20260812T010203Z",
        )


def test_backup_failure_message_hides_connection_details(tmp_path: Path):
    """失败原因要能看懂，但不能把主机地址、库口令泄露到控制台/日志。"""
    with pytest.raises(BackupValidationError) as excinfo:
        create_and_verify_backup(
            "postgresql://erp_user:secret@127.0.0.1:15432/xihong_erp",
            _state(),
            backup_directory=tmp_path,
            docker_runner=FailingDumpRunner(),
            now=lambda: "20260812T010203Z",
        )

    message = str(excinfo.value)
    assert "sup3rs3cret" not in message
    assert "10.11.12.13" not in message
    assert "password=***" in message


def test_failure_reason_redacts_urls_and_addresses():
    reason = _safe_failure_reason(
        "pg_dump: error: could not connect to "
        "postgresql://erp_user:pw@db.internal:5432/xihong_erp"
    )

    assert "erp_user" not in reason
    assert "db.internal" not in reason
    assert "<connection>" in reason


def test_failure_reason_redacts_passwords_and_addresses():
    reason = _safe_failure_reason(
        "pg_dump: error: connection to server at 10.11.12.13 (10.11.12.13), "
        "port 5432 failed: password=sup3rs3cret dbname=xihong_erp"
    )

    assert "sup3rs3cret" not in reason
    assert "10.11.12.13" not in reason
    assert "password=***" in reason


def test_failure_reason_without_diagnostics_is_explicit():
    assert _safe_failure_reason(None) == "no diagnostic output"
    assert _safe_failure_reason("   ") == "no diagnostic output"
