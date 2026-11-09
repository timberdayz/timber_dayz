"""契约测试：发版链的前端开关、迁移前备份、演练 fail-closed、生产 compose 配置。

这些是"发版能不能安全上线"的闸门，任何一条被悄悄改掉都会让线上回到
"前端没发 / 没备份 / 没演练也绿灯"的状态，所以用契约测试钉死。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.local_migration_backup import (
    DUMP_MODE_DIRECT,
    DUMP_MODE_DOCKER,
    BackupValidationError,
    create_and_verify_backup,
)
from scripts.rehearsal_prod_snapshot import main as rehearsal_main


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_remote_production.sh"
REHEARSAL_SCRIPT = ROOT / "scripts" / "rehearsal_prod_snapshot.py"
LOCAL_VERIFY_SCRIPT = ROOT / "scripts" / "verify_release_local.py"
BUNDLE_SCRIPT = ROOT / "scripts" / "build_deploy_bundle.sh"
PROD_COMPOSE = ROOT / "docker-compose.prod.yml"


def _deploy_script() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 任务一：发版总链接入前端（显式开关 + 缺依赖即失败）
# --------------------------------------------------------------------------


def test_deploy_script_exposes_an_explicit_skip_frontend_switch():
    script = _deploy_script()

    assert "--skip-frontend" in script
    assert "SKIP_FRONTEND=0" in script
    assert "Unknown argument" in script, "未知参数必须 fail-closed，不能静默忽略"


def test_deploy_script_fails_loudly_when_frontend_dependencies_are_missing():
    script = _deploy_script()

    assert "node_modules" in script
    assert "cd frontend && npm ci" in script, "缺依赖必须给出可执行的安装指引"
    assert "[FAIL] Frontend dependencies are missing" in script


def test_deploy_script_keeps_the_frontend_in_the_release_by_default():
    script = _deploy_script()

    # 默认路径必须仍然包含前端镜像拉取与前端容器启动。
    assert "up -d --no-build --no-deps frontend" in script
    assert "Pulling frontend image..." in script
    # 跳过时前端镜像不拉、也不替换正在运行的前端容器。
    assert "skipping the frontend image pull" in script
    assert "keeping the currently running frontend container" in script


# --------------------------------------------------------------------------
# 任务二：跑迁移前必须先备份，且备份必须可恢复
# --------------------------------------------------------------------------


def test_deploy_script_backs_up_before_running_the_migration():
    script = _deploy_script()

    backup_index = script.index("perform_pre_migration_backup")
    migrate_index = script.index("Phase 2: Running smart database migration")
    stage_index = script.index("stage_running_application_containers")
    assert stage_index < backup_index < migrate_index, "备份必须是跑迁移前的必经步骤"
    assert "Pre-migration backup failed; the migration is blocked" in script


def test_deploy_script_ships_the_backup_tool_to_the_server():
    bundle = BUNDLE_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/local_migration_backup.py" in bundle


def test_backup_transports_cover_docker_exec_and_direct_client():
    script = _deploy_script()

    assert "--dump-mode docker" in script
    assert "--dump-mode direct" in script
    assert "pg_restore --list" in script or "pg_restore" in script


class _RecordingClientRunner:
    """记录 direct 传输的命令，并伪造一个 dump 产物。"""

    def __init__(self, *, restore_exit_code: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []
        self.restore_exit_code = restore_exit_code

    def __call__(self, command: list[str], **kwargs):
        self.commands.append(command)
        self.kwargs.append(kwargs)
        if command[0] == "pg_dump":
            Path(command[command.index("-f") + 1]).write_bytes(b"PGDMP-direct")
        return type(
            "Result",
            (),
            {
                "returncode": self.restore_exit_code
                if command[0] == "pg_restore"
                else 0,
                "stderr": "",
            },
        )()


def _state():
    class _State:
        database_empty = False
        current_revision = None
        legacy_revision = "legacy-revision"
        schema_fingerprint = "fingerprint"

    return _State()


def test_direct_transport_uses_client_binaries_without_leaking_the_password(tmp_path):
    runner = _RecordingClientRunner()

    metadata = create_and_verify_backup(
        "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        dump_mode=DUMP_MODE_DIRECT,
        client_runner=runner,
        now=lambda: "20261109T010203Z",
    )

    assert metadata["dump_mode"] == DUMP_MODE_DIRECT
    assert metadata["verification"] == "pg_restore_list_passed"
    assert any(command[0] == "pg_dump" for command in runner.commands)
    assert any(command[0] == "pg_restore" for command in runner.commands)
    for command in runner.commands:
        assert "sup3rs3cret" not in " ".join(command), "口令不能出现在命令行里"
    dump_kwargs = next(
        kwargs
        for command, kwargs in zip(runner.commands, runner.kwargs)
        if command[0] == "pg_dump"
    )
    assert dump_kwargs["env"]["PGPASSWORD"] == "sup3rs3cret"
    assert "lock_timeout=60s" in dump_kwargs["env"]["PGOPTIONS"]


def test_direct_transport_rejects_an_unreadable_archive(tmp_path):
    runner = _RecordingClientRunner(restore_exit_code=1)

    with pytest.raises(BackupValidationError, match="pg_restore --list failed"):
        create_and_verify_backup(
            "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
            _state(),
            backup_directory=tmp_path,
            dump_mode=DUMP_MODE_DIRECT,
            client_runner=runner,
            now=lambda: "20261109T010203Z",
        )


def test_every_backup_run_gets_its_own_timestamped_directory(tmp_path):
    runner = _RecordingClientRunner()

    first = create_and_verify_backup(
        "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        dump_mode=DUMP_MODE_DIRECT,
        client_runner=runner,
        now=lambda: "20261109T010203Z",
    )
    second = create_and_verify_backup(
        "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        dump_mode=DUMP_MODE_DIRECT,
        client_runner=runner,
        now=lambda: "20261109T010203Z",
    )

    first_dir = Path(first["backup_path"]).parent
    second_dir = Path(second["backup_path"]).parent
    assert first_dir != second_dir, "同名时间戳也不能覆盖历史备份"
    assert first_dir.parent == tmp_path
    assert second_dir.parent == tmp_path


def test_docker_transport_stays_the_default_for_the_local_migration_guard(tmp_path):
    runner = _RecordingDockerRunner()

    metadata = create_and_verify_backup(
        "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        docker_runner=runner,
        now=lambda: "20261109T010203Z",
    )

    assert metadata["dump_mode"] == DUMP_MODE_DOCKER
    assert metadata["verification"] == "pg_restore_list_passed"
    assert any("pg_dump" in command for command in runner.commands)
    assert any("pg_restore" in command for command in runner.commands)


class _RecordingDockerRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs):
        self.commands.append(command)
        if command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_bytes(b"PGDMP-docker")
        return type(
            "Result",
            (),
            {"returncode": 0, "stderr": ""},
        )()


# --------------------------------------------------------------------------
# 任务三：演练 fail-open → fail-closed
# --------------------------------------------------------------------------


def test_rehearsal_without_snapshot_fails_closed(monkeypatch, capsys):
    monkeypatch.delenv("PROD_SNAPSHOT_DATABASE_URL", raising=False)

    assert rehearsal_main([]) != 0
    captured = capsys.readouterr().out
    assert "PROD_SNAPSHOT_DATABASE_URL" in captured
    assert "[FAIL]" in captured


def test_rehearsal_can_only_be_skipped_with_the_explicit_switch(monkeypatch, capsys):
    monkeypatch.delenv("PROD_SNAPSHOT_DATABASE_URL", raising=False)

    assert rehearsal_main(["--allow-skip"]) == 0
    assert "--allow-skip" in capsys.readouterr().out


def test_local_release_chain_may_skip_the_optional_snapshot():
    text = LOCAL_VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert "rehearsal_prod_snapshot.py" in text
    assert "--allow-skip" in text


def test_production_release_chain_never_passes_the_skip_switch():
    deploy = _deploy_script()
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text(
        encoding="utf-8", errors="replace"
    )

    assert "--allow-skip" not in deploy
    assert "--allow-skip" not in workflow


# --------------------------------------------------------------------------
# 任务四：生产 compose 的连接数与日志轮转
# --------------------------------------------------------------------------


def test_production_postgres_raises_max_connections():
    text = PROD_COMPOSE.read_text(encoding="utf-8")

    assert "max_connections=200" in text
    assert "max_connections=80" not in text


def _service_block(text: str, service: str) -> str:
    """Return the raw compose block of one service (2-space indented keys)."""
    lines = text.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(f"  {service}:")
    )
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


@pytest.mark.parametrize(
    "service",
    [
        "postgres",
        "redis",
        "backend-api",
        "celery-worker",
        "celery-beat",
        "frontend",
        "nginx",
    ],
)
def test_production_services_have_bounded_container_logs(service):
    text = PROD_COMPOSE.read_text(encoding="utf-8")
    service_block = _service_block(text, service)

    assert "logging:" in service_block, f"{service} 缺少日志轮转配置"
    assert "json-file" in service_block
    assert "max-size" in service_block
    assert "max-file" in service_block


def test_backup_metadata_never_stores_the_connection_password(tmp_path):
    runner = _RecordingClientRunner()

    metadata = create_and_verify_backup(
        "postgresql://erp_user:sup3rs3cret@127.0.0.1:15432/xihong_erp",
        _state(),
        backup_directory=tmp_path,
        dump_mode=DUMP_MODE_DIRECT,
        client_runner=runner,
        now=lambda: "20261109T010203Z",
    )

    text = Path(metadata["metadata_path"]).read_text(encoding="utf-8")
    assert "sup3rs3cret" not in text
    assert json.loads(text)["verification"] == "pg_restore_list_passed"
