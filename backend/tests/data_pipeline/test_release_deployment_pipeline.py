from pathlib import Path


def test_deploy_workflow_syncs_nginx_prod_conf():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "nginx/nginx.prod.conf" in text


def test_remote_deploy_script_cleans_legacy_metabase_container():
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "xihong_erp_metabase" in text
    assert "docker stop xihong_erp_metabase" in text or "docker rm xihong_erp_metabase" in text


def test_backend_dockerfile_includes_ops_dashboard_scripts():
    text = Path("Dockerfile.backend").read_text(encoding="utf-8", errors="replace")

    assert "check_postgresql_dashboard_ops.py" in text
    assert "smoke_postgresql_dashboard_routes.py" in text
