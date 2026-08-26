from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "scripts" / "backend-entrypoint.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"


def test_backend_entrypoint_distinguishes_service_from_one_off_commands():
    script = ENTRYPOINT.read_text(encoding="utf-8")

    assert "is_backend_service_command" in script
    assert "Starting backend service" in script
    assert "Running one-off command" in script
    assert 'case "$1" in' in script
    assert "gunicorn|uvicorn" in script


def test_deploy_workflow_runs_backend_container_smoke_before_remote_deploy():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "Backend container startup smoke" in workflow
    assert "import backend.main" in workflow
    assert "gunicorn backend.main:app" in workflow
    assert "xihong_erp_backend_smoke_postgres" in workflow
    assert "xihong_erp_backend_smoke_redis" in workflow


def test_deploy_workflow_executes_backup_variables_only_on_remote_shell():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("<<'REMOTE_BACKUP'") == 2
    assert workflow.count('production_path="$1"') == 2
    assert workflow.count('backup_dir="backups/pre_deploy_$(date +%Y%m%d_%H%M%S)"') == 2
    assert 'mkdir -p "${BACKUP_DIR}"' not in workflow


def test_production_nginx_healthcheck_uses_local_tls_without_certificate_verification():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "--no-check-certificate" in compose
    assert "https://127.0.0.1/" in compose
