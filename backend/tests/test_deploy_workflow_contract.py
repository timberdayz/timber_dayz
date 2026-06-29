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
