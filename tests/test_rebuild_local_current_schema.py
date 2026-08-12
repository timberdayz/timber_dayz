from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import rebuild_local_current_schema as rebuild


DATABASE_URL = "postgresql://erp_user:password@127.0.0.1:15432/xihong_erp"


@pytest.fixture(autouse=True)
def local_docker_context(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(
        rebuild,
        "_docker_context_endpoint",
        lambda: "npipe:////./pipe/dockerDesktopLinuxEngine",
    )


def _docker_port_mapping() -> str:
    return '{"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]}'


def _successful_docker_runner(command, **_kwargs):
    if command[1:3] == ["inspect", "--format"]:
        return SimpleNamespace(returncode=0, stdout=_docker_port_mapping(), stderr="")
    if "pg_stat_activity" in " ".join(command):
        return SimpleNamespace(returncode=0, stdout="0\n", stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_rebuild_rejects_missing_confirmation_before_backup_or_docker_commands():
    calls: list[list[str]] = []

    with pytest.raises(rebuild.RebuildSafetyError, match="confirmation"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation="wrong",
            docker_runner=lambda command, **_kwargs: calls.append(command),
        )

    assert not any("dropdb" in command for command in calls)


def test_rebuild_cli_shows_read_only_plan_without_confirmation(capsys):
    assert rebuild.main([]) == 2

    plan = capsys.readouterr().out
    assert '"action": "rebuild_local_current_schema"' in plan
    assert '"database": "xihong_erp"' in plan
    assert rebuild.CONFIRMATION_PHRASE not in plan


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


def test_rebuild_rejects_unparseable_database_url_before_docker_commands():
    with pytest.raises(rebuild.RebuildSafetyError, match="PostgreSQL URL"):
        rebuild.rebuild_local_current_schema(
            "not a database URL",
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda *_args, **_kwargs: pytest.fail("docker must not run"),
        )


def test_rebuild_rejects_remote_docker_daemon_before_backup_or_drop(monkeypatch):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    monkeypatch.setattr(rebuild, "_docker_context_endpoint", lambda: "tcp://remote:2376")

    with pytest.raises(rebuild.RebuildSafetyError, match="local Docker daemon"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=lambda *_args, **_kwargs: pytest.fail("docker must not run"),
        )


def test_rebuild_rejects_container_without_expected_database_port_mapping(monkeypatch):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout='{"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "25432"}]}',
            stderr="",
        )

    with pytest.raises(rebuild.RebuildSafetyError, match="port mapping"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=runner,
        )

    assert not any("dropdb" in command for command in calls)


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


def test_rebuild_cli_loads_collection_environment_before_resolving_database_url(
    monkeypatch, tmp_path: Path
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    captured: dict[str, str] = {}
    (tmp_path / ".env.collection.local").write_text(
        "DATABASE_URL=postgresql://erp_user:password@127.0.0.1:15432/xihong_erp\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "ROOT", tmp_path)
    monkeypatch.setattr(
        rebuild,
        "rebuild_local_current_schema",
        lambda database_url, *, confirmation: captured.update(
            database_url=database_url, confirmation=confirmation
        )
        or {"database": "xihong_erp"},
    )

    assert rebuild.main(["--confirm", rebuild.CONFIRMATION_PHRASE]) == 0
    assert captured == {
        "database_url": "postgresql://erp_user:password@127.0.0.1:15432/xihong_erp",
        "confirmation": rebuild.CONFIRMATION_PHRASE,
    }
    assert os.getenv("DATABASE_URL") == captured["database_url"]


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
        if command[1:3] == ["inspect", "--format"]:
            return SimpleNamespace(returncode=0, stdout=_docker_port_mapping(), stderr="")
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
                or _successful_docker_runner(command)
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
                or _successful_docker_runner(command)
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
        if command[1:3] == ["inspect", "--format"]:
            return SimpleNamespace(returncode=0, stdout=_docker_port_mapping(), stderr="")
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


def test_rebuild_reenables_connections_when_a_competing_connection_appears(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rebuild, "_local_collection_backend_running", lambda _iterator: False)
    calls: list[list[str]] = []
    state = SimpleNamespace(
        database_empty=False,
        legacy_revision="legacy",
        current_revision=None,
        schema_fingerprint="fingerprint",
    )

    def runner(command, **_kwargs):
        calls.append(command)
        command_text = " ".join(command)
        if command[1:3] == ["inspect", "--format"]:
            return SimpleNamespace(returncode=0, stdout=_docker_port_mapping(), stderr="")
        if "pg_stat_activity" in command_text:
            count = "0\n" if sum("pg_stat_activity" in " ".join(item) for item in calls) == 1 else "1\n"
            return SimpleNamespace(returncode=0, stdout=count, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(rebuild.RebuildSafetyError, match="active connections"):
        rebuild.rebuild_local_current_schema(
            DATABASE_URL,
            confirmation=rebuild.CONFIRMATION_PHRASE,
            docker_runner=runner,
            migration_state_probe=lambda _url: state,
            backup_creator=lambda *_args, **_kwargs: {
                "metadata_path": str(tmp_path / "backup.json"),
                "backup_sha256": "a" * 64,
                "source_database": "xihong_erp",
            },
            backup_verifier=lambda *_args, **_kwargs: {},
        )

    command_texts = [" ".join(command) for command in calls]
    assert any("ALLOW_CONNECTIONS false" in command for command in command_texts)
    assert any("ALLOW_CONNECTIONS true" in command for command in command_texts)
    assert not any("dropdb" in command for command in command_texts)
