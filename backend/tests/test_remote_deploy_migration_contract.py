from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_remote_production.sh"
BACKEND_DOCKERFILE = ROOT / "Dockerfile.backend"


def _deploy_script() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def test_remote_deploy_prefers_core_alembic_version_detection():
    script = _deploy_script()

    assert "table_schema = 'core' AND table_name = 'alembic_version'" in script
    assert "CORE_ALEMBIC_VERSION_EXISTS" in script
    assert "PUBLIC_ALEMBIC_VERSION_EXISTS" in script
    assert "ALEMBIC_VERSION_EXISTS=$(" not in script


def test_remote_deploy_fails_fast_when_business_tables_exist_without_alembic_version():
    script = _deploy_script()

    assert "BUSINESS_TABLE_COUNT" in script
    assert "DATABASE_IS_EMPTY" in script
    assert "[ERROR] No alembic_version table found, but database is not empty" in script
    assert "return 1" in script


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
    assert "docker inspect xihong_erp_backend_api" in script
    assert "docker logs xihong_erp_backend_api --tail 300" in script
    assert "tail -n 300 /app/logs/error.log" in script
    assert "tail -n 200 /app/logs/access.log" in script


def test_backend_gunicorn_errors_are_written_to_container_stderr():
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert '"--error-logfile", "-"' in dockerfile
