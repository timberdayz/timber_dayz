from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import rebuild_local_current_schema as rebuild


DATABASE_URL = "postgresql://erp_user:password@127.0.0.1:15432/xihong_erp"


def test_rebuild_rejects_missing_confirmation_before_backup_or_docker_commands():
    calls: list[list[str]] = []

    with pytest.raises(rebuild.RebuildSafetyError, match="confirmation"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation="wrong",
            docker_runner=lambda command, **_kwargs: calls.append(command),
        )

    assert not any("dropdb" in command for command in calls)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://erp_user:password@example.com:15432/xihong_erp",
        "postgresql://erp_user:password@127.0.0.1:15432/not_xihong_erp",
        "postgresql://erp_user:password@127.0.0.1:15432/xihong_erp?host=example.com",
    ],
)
def test_rebuild_rejects_non_local_or_unexpected_database_before_backup(database_url: str):
    with pytest.raises(rebuild.RebuildSafetyError):
        rebuild.rebuild_local_current_schema(
            database_url,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda *_args, **_kwargs: pytest.fail("docker must not run"),
        )


def test_rebuild_accepts_loopback_asyncpg_postgresql_url():
    database, username = rebuild._validate_local_target(
        "postgresql+asyncpg://erp_user:password@127.0.0.1:15432/xihong_erp"
    )

    assert database == "xihong_erp"
    assert username == "erp_user"


def test_rebuild_normalizes_accepted_postgresql_driver_to_sync_url():
    database_url = rebuild._normalized_local_database_url(
        "postgresql+asyncpg://erp_user:password@127.0.0.1:15432/xihong_erp"
    )

    assert database_url.startswith("postgresql://")
    assert "+asyncpg" not in database_url


def test_rebuild_rejects_an_active_local_collection_backend_before_backup(monkeypatch):
    monkeypatch.setattr(
        rebuild,
        "_local_collection_backend_running",
        lambda _process_iterator: True,
    )

    with pytest.raises(rebuild.RebuildSafetyError, match="backend"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda *_args, **_kwargs: pytest.fail("docker must not run"),
        )


def test_rebuild_rejects_active_database_connections_before_drop(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        if "pg_stat_activity" in " ".join(command):
            return SimpleNamespace(returncode=0, stdout="1\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(rebuild.RebuildSafetyError, match="active connections"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=runner,
            backup_creator=lambda *_args, **_kwargs: {"metadata_path": str(tmp_path / "backup.json")},
            backup_verifier=lambda *_args, **_kwargs: {},
        )

    assert not any(command[3] == "dropdb" for command in calls if len(command) > 3)


def test_rebuild_stops_when_backup_validation_fails_before_drop(monkeypatch):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []
    state = SimpleNamespace(
        database_empty=False,
        legacy_revision="legacy",
        current_revision=None,
        schema_fingerprint="fingerprint",
    )
    rebuilt_state = SimpleNamespace(
        database_empty=False,
        legacy_revision=None,
        current_revision="current_schema_20260810_operation_contract_isolation",
        schema_fingerprint="new-fingerprint",
    )
    probe_results = iter([state, rebuilt_state])

    with pytest.raises(rebuild.RebuildSafetyError, match="backup"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda command, **_kwargs: (
                calls.append(command)
                or SimpleNamespace(returncode=0, stdout="0\n", stderr="")
            ),
            backup_creator=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                rebuild.BackupValidationError("backup unreadable")
            ),
            migration_state_probe=lambda _url: next(probe_results),
        )

    assert not any("dropdb" in command for command in calls)


def test_rebuild_rejects_backup_from_another_database_before_drop(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []
    state = SimpleNamespace(
        database_empty=False,
        legacy_revision="legacy",
        current_revision=None,
        schema_fingerprint="fingerprint",
    )

    with pytest.raises(rebuild.RebuildSafetyError, match="database does not match"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda command, **_kwargs: (
                calls.append(command)
                or SimpleNamespace(returncode=0, stdout="0\n", stderr="")
            ),
            migration_state_probe=lambda _url: state,
            backup_creator=lambda *_args, **_kwargs: {
                "metadata_path": str(tmp_path / "backup.json"),
                "backup_sha256": "a" * 64,
                "source_database": "other_database",
            },
            backup_verifier=lambda *_args, **_kwargs: {},
        )

    assert not any("dropdb" in command for command in calls)


def test_rebuild_runs_only_fixed_local_drop_create_then_bootstraps(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []
    receipts = tmp_path / "receipts"
    state = SimpleNamespace(
        database_empty=False,
        legacy_revision="legacy",
        current_revision=None,
        schema_fingerprint="fingerprint",
    )
    rebuilt_state = SimpleNamespace(
        database_empty=False,
        legacy_revision=None,
        current_revision="current_schema_20260810_operation_contract_isolation",
        schema_fingerprint="new-fingerprint",
    )
    probe_results = iter([state, rebuilt_state])

    def runner(command, **_kwargs):
        calls.append(command)
        if "pg_stat_activity" in " ".join(command):
            return SimpleNamespace(returncode=0, stdout="0\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = rebuild.rebuild_local_current_schema(
        DATABASE_URL,
        confirmation=rebuild.CONFIRMATION_PHRASE,
        docker_runner=runner,
        migration_state_probe=lambda _url: next(probe_results),
        backup_creator=lambda *_args, **_kwargs: {
            "metadata_path": str(tmp_path / "backup.json"),
            "backup_sha256": "a" * 64,
            "source_database": "xihong_erp",
        },
        backup_verifier=lambda *_args, **_kwargs: {},
        command_runner=lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                '{"ready": true}' if "--check" in command else "{}"
            ),
            stderr="",
        ),
        receipt_directory=receipts,
    )

    assert any(command[3:5] == ["dropdb", "-U"] for command in calls)
    assert any(command[3:5] == ["createdb", "-U"] for command in calls)
    assert sum("pg_stat_activity" in " ".join(command) for command in calls) == 2
    assert result["database"] == "xihong_erp"
    assert result["backup_sha256"] == "a" * 64
    assert Path(result["receipt_path"]).is_file()
