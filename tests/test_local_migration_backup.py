from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from scripts.local_migration_backup import (
    BackupValidationError,
    create_and_verify_backup,
    verify_backup_metadata,
)
from scripts.run_current_schema_migrations import MigrationState


class RecordingRunner:
    def __init__(self, *, restore_exit_code: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.restore_exit_code = restore_exit_code

    def __call__(self, command: list[str], **_kwargs):
        self.commands.append(command)
        if command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_bytes(b"PGDMP-test-backup")
        return type("Result", (), {"returncode": self.restore_exit_code if "pg_restore" in command else 0, "stderr": ""})()


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

    with pytest.raises(BackupValidationError, match="schema fingerprint does not match"):
        verify_backup_metadata(metadata_path, _state())


def test_backup_tool_has_a_read_only_metadata_verification_cli_contract():
    source = Path("scripts/local_migration_backup.py").read_text(encoding="utf-8")

    assert "--verify-metadata" in source
    assert "--database-url" in source
    assert "if __name__ == \"__main__\"" in source
