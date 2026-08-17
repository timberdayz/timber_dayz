from pathlib import Path

import scripts.run_current_schema_migrations as migration_runner


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_remote_production.sh"
BACKEND_DOCKERFILE = ROOT / "Dockerfile.backend"


def _deploy_script() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def test_remote_deploy_uses_fail_closed_current_schema_wrapper():
    script = _deploy_script()

    assert "run_current_schema_migrations.py" in script
    assert "CURRENT_SCHEMA_SOURCE_REVISION" in script
    assert "CURRENT_SCHEMA_SOURCE_FINGERPRINT" in script
    assert "alembic upgrade heads" not in script


def test_remote_deploy_passes_optional_current_schema_source_contract_to_wrapper():
    script = _deploy_script()

    assert "-e CURRENT_SCHEMA_SOURCE_REVISION" in script
    assert "-e CURRENT_SCHEMA_SOURCE_FINGERPRINT" in script
    assert "CURRENT_SCHEMA_SOURCE_REVISION is required" not in script
    assert "CURRENT_SCHEMA_SOURCE_FINGERPRINT is required" not in script


def test_remote_deploy_schema_gate_runs_before_backend_health_wait():
    script = _deploy_script()

    gate_index = script.index("verify_schema_completeness")
    health_index = script.index("[INFO] Waiting for backend health...")
    assert gate_index < health_index
    assert "migration_status" in script
    assert "missing_columns" in script
    assert "SCHEMA_GATE_RC" in script


def test_remote_deploy_backend_timeout_outputs_actionable_container_diagnostics():
    script = _deploy_script()

    assert "docker ps -a --filter name=xihong_erp_backend_api" in script
    assert "docker inspect xihong_erp_backend_api --format '{{json .State}}'" in script
    assert "docker logs --timestamps --tail 1000 xihong_erp_backend_api" in script
    assert "docker cp xihong_erp_backend_api:/app/logs/error.log" in script
    assert "docker cp xihong_erp_backend_api:/app/logs/access.log" in script


def test_remote_deploy_validates_cleaned_env_values_are_unquoted():
    script = _deploy_script()

    assert "validate_cleaned_env_quotes" in script
    assert "DATABASE_URL REDIS_URL SECRET_KEY JWT_SECRET_KEY" in script
    assert "must not be wrapped in literal quotes" in script


def test_backend_gunicorn_errors_are_written_to_container_stderr():
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert '"--error-logfile", "-"' in dockerfile


def test_backend_image_includes_current_schema_migration_helper_module():
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY scripts/run_current_schema_migrations.py /app/scripts/run_current_schema_migrations.py" in dockerfile
    assert "COPY scripts/local_migration_backup.py /app/scripts/local_migration_backup.py" in dockerfile


def test_current_schema_preflight_only_performs_read_only_adoption_checks(monkeypatch):
    state = migration_runner.MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision="approved-legacy",
        schema_fingerprint="approved-fingerprint",
    )
    safety_checks: list[str] = []

    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(
        migration_runner,
        "choose_migration_action",
        lambda *_args, **_kwargs: "stamp",
    )
    monkeypatch.setattr(
        migration_runner,
        "get_supported_current_revisions",
        lambda: {"current_schema_20260805"},
    )
    monkeypatch.setattr(
        migration_runner,
        "assert_legacy_adoption_data_is_safe",
        lambda database_url: safety_checks.append(database_url),
    )
    monkeypatch.setattr(
        migration_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preflight-only must not invoke Alembic")
        ),
    )

    assert (
        migration_runner.preflight_current_schema_migrations(
            "postgresql://example",
            expected_source_revision="approved-legacy",
            expected_source_fingerprint="approved-fingerprint",
        )
        == "stamp"
    )
    assert safety_checks == ["postgresql://example"]


def test_current_schema_preflight_checks_current_revision_contract_before_upgrade(
    monkeypatch,
):
    state = migration_runner.MigrationState(
        database_empty=False,
        current_revision="current_schema_20260808_operation_performance_workbench",
        legacy_revision=None,
        schema_fingerprint="current-fingerprint",
    )
    safety_checks: list[str] = []
    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(
        migration_runner,
        "choose_migration_action",
        lambda *_args, **_kwargs: "upgrade",
    )
    monkeypatch.setattr(
        migration_runner,
        "get_supported_current_revisions",
        lambda: {state.current_revision},
    )
    monkeypatch.setattr(
        migration_runner,
        "assert_legacy_adoption_data_is_safe",
        lambda database_url: safety_checks.append(database_url),
    )

    assert (
        migration_runner.preflight_current_schema_migrations(
            "postgresql://current",
            expected_source_revision=None,
            expected_source_fingerprint=None,
        )
        == "upgrade"
    )
    assert safety_checks == ["postgresql://current"]


def test_current_schema_preflight_cli_never_invokes_the_migration_writer(monkeypatch):
    monkeypatch.setattr(
        migration_runner,
        "preflight_current_schema_migrations",
        lambda *_args, **_kwargs: "upgrade",
    )
    monkeypatch.setattr(
        migration_runner,
        "run_current_schema_migrations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("--preflight-only must not invoke the migration writer")
        ),
    )
    monkeypatch.setattr(
        migration_runner.sys,
        "argv",
        [
            "run_current_schema_migrations.py",
            "--database-url",
            "postgresql://example",
            "--preflight-only",
        ],
    )

    assert migration_runner.main() == 0


def test_current_schema_preflight_does_not_log_legacy_operation_record_ids(
    monkeypatch, capsys
):
    state = migration_runner.MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision="approved-legacy",
        schema_fingerprint="approved-fingerprint",
    )
    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(
        migration_runner,
        "choose_migration_action",
        lambda *_args, **_kwargs: "stamp",
    )
    monkeypatch.setattr(
        migration_runner,
        "get_supported_current_revisions",
        lambda: {"current_schema_20260805"},
    )
    monkeypatch.setattr(
        migration_runner,
        "assert_legacy_adoption_data_is_safe",
        lambda _database_url: {
            "legacy_count": 1,
            "missing_metric_code": {"ids": [101]},
        },
    )

    migration_runner.preflight_current_schema_migrations(
        "postgresql://example",
        expected_source_revision="approved-legacy",
        expected_source_fingerprint="approved-fingerprint",
    )

    assert "101" not in capsys.readouterr().out


def test_remote_deploy_preflights_before_stopping_or_removing_application_containers():
    script = _deploy_script()

    preflight_index = script.index("run_current_schema_migrations.py --preflight-only")
    stage_index = script.index("stage_running_application_containers", preflight_index)
    assert preflight_index < stage_index
    assert "docker rm xihong_erp_frontend" not in script
    assert "-e CURRENT_SCHEMA_SOURCE_REVISION" in script
    assert "-e CURRENT_SCHEMA_SOURCE_FINGERPRINT" in script


def test_remote_deploy_restores_previously_running_application_containers_on_cutover_failure():
    script = _deploy_script()

    for container in (
        "xihong_erp_frontend",
        "xihong_erp_nginx",
        "xihong_erp_backend_api",
        "xihong_erp_celery_worker",
        "xihong_erp_celery_beat",
    ):
        assert container in script
    assert "capture_running_application_containers" in script
    assert "restore_previous_application_containers" in script
    assert "handle_deploy_exit" in script
    assert "trap handle_deploy_exit EXIT" in script
    assert "DEPLOYMENT_CUTOVER_COMPLETE=1" in script


def test_remote_deploy_isolates_new_compose_project_from_rollback_container_ids():
    script = _deploy_script()

    assert "DEPLOYMENT_COMPOSE_PROJECT" in script
    assert '"-p" "${DEPLOYMENT_COMPOSE_PROJECT}"' in script
    assert "old containers retain their original Compose labels" in script
    assert 'docker inspect "${previous_id}"' in script
    assert 'docker rename "${previous_id}" "${backup_name}"' in script
    assert script.index(
        "run_current_schema_migrations.py --preflight-only"
    ) < script.index('compose_cmd_base=("${compose_cmd_base[@]}" "-p"')


def test_remote_deploy_release_overlay_shares_but_never_owns_infrastructure_network():
    script = _deploy_script()

    assert (
        "networks:\n  erp_network:\n    external: true\n    name: xihong_erp_erp_network"
        in script
    )
    assert '"${infra_compose_cmd[@]}" up -d --no-build postgres redis' in script
    assert '"${compose_cmd_base[@]}" up -d --no-build postgres redis' not in script
    assert "docker network inspect xihong_erp_erp_network >/dev/null 2>&1" in script
    preflight_phase_index = script.index(
        'echo "[INFO] Phase 1.5: Running read-only current-schema migration preflight..."'
    )
    assert script.index(
        'compose_cmd_base=("${compose_cmd_base[@]}" "-p"', preflight_phase_index
    ) < script.index("if ! preflight_current_schema_migrations;", preflight_phase_index)


def test_isolated_release_starts_application_services_without_compose_dependencies():
    script = _deploy_script()

    for service in ("backend-api celery-worker celery-beat", "frontend", "nginx"):
        assert f"up -d --no-build --no-deps {service}" in script


def test_remote_deploy_requires_frontend_and_gateway_health_before_declaring_cutover():
    script = _deploy_script()

    cutover_index = script.index("DEPLOYMENT_CUTOVER_COMPLETE=1")
    assert "[FAIL] Frontend health check failed" in script
    assert "[FAIL] Nginx health check failed" in script
    assert "[FAIL] Nginx config test failed" in script
    assert script.index("[FAIL] Frontend health check failed") < cutover_index
    assert script.index("[FAIL] Nginx health check failed") < cutover_index
    assert script.index("[FAIL] Nginx config test failed") < cutover_index


def test_remote_deploy_uses_a_valid_bash_rollback_suffix_and_frontend_probe_tool():
    script = _deploy_script()

    assert 'DEPLOYMENT_ROLLBACK_SUFFIX="$$_$(date +%s)"' in script
    assert "${$}" not in script
    assert (
        "docker exec xihong_erp_frontend wget --quiet --tries=1 "
        "--output-document=/dev/null http://127.0.0.1/" in script
    )
    assert "docker exec xihong_erp_frontend curl" not in script
