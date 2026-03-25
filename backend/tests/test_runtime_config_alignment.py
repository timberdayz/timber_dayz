from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_dev_backend_mounts_tools_directory():
    compose = _read_yaml("docker-compose.dev.yml")
    volumes = compose["services"]["backend"]["volumes"]

    assert any(
        str(volume).startswith("./tools:/app/tools")
        for volume in volumes
    ), "backend dev container must mount tools into /app/tools for runtime subprocesses"


def test_backend_image_copies_runtime_tool_scripts():
    dockerfile = (PROJECT_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")

    assert (
        "COPY tools /app/tools" in dockerfile
        or "COPY tools/launch_inspector_recorder.py /app/tools/launch_inspector_recorder.py" in dockerfile
    ), "backend image must package runtime tools into /app/tools"

    assert (
        "COPY tools /app/tools" in dockerfile
        or "COPY tools/run_component_test.py /app/tools/run_component_test.py" in dockerfile
    ), "backend image must package component test runner into /app/tools"


def test_prod_compose_uses_container_internal_database_urls():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend"]["environment"]
    worker_env = compose["services"]["celery-worker"]["environment"]

    assert backend_env["DATABASE_URL"] == "${DATABASE_URL}"
    assert worker_env["DATABASE_URL"] == "${DATABASE_URL}"


def test_prod_compose_does_not_keep_legacy_secret_fallbacks():
    compose_text = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "erp_pass_2025" not in compose_text
    assert "redis_pass_2025" not in compose_text
    assert "xihong-erp-secret-key-prod-2025" not in compose_text
    assert "xihong-erp-jwt-secret-prod-2025" not in compose_text


def test_prod_compose_forces_production_runtime_mode():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend"]["environment"]
    worker_env = compose["services"]["celery-worker"]["environment"]

    assert backend_env["ENVIRONMENT"] == "production"
    assert backend_env["APP_ENV"] == "production"
    assert worker_env["ENVIRONMENT"] == "production"


def test_prod_compose_allows_backend_host_for_nginx_proxy():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend"]["environment"]

    assert backend_env["ALLOWED_HOSTS"].endswith(",backend")


def test_dev_compose_allows_backend_host_for_nginx_proxy():
    compose = _read_yaml("docker-compose.dev.yml")
    backend_env = compose["services"]["backend"]["environment"]

    assert backend_env["ALLOWED_HOSTS"].endswith(",backend")


def test_dev_celery_healthcheck_does_not_depend_on_ps_binary():
    compose = _read_yaml("docker-compose.dev.yml")
    health_test = compose["services"]["celery-worker"]["healthcheck"]["test"]

    assert "ps aux" not in " ".join(str(part) for part in health_test)


def test_cloud_overlay_increases_celery_beat_memory_limit():
    compose = _read_yaml("docker-compose.cloud.yml")
    beat_limits = compose["services"]["celery-beat"]["deploy"]["resources"]["limits"]

    assert beat_limits["memory"] == "256M"


def test_cloud_4c8g_overlay_sets_balanced_backend_and_worker_memory_limits():
    compose = _read_yaml("docker-compose.cloud-4c8g.yml")

    backend_limits = compose["services"]["backend"]["deploy"]["resources"]["limits"]
    worker_limits = compose["services"]["celery-worker"]["deploy"]["resources"]["limits"]

    assert backend_limits["memory"] == "1.5G"
    assert worker_limits["memory"] == "768M"


def test_remote_production_deploy_does_not_start_celery_exporter_by_default():
    deploy_script = (
        PROJECT_ROOT / "scripts" / "deploy_remote_production.sh"
    ).read_text(encoding="utf-8")

    assert 'up -d backend celery-worker celery-beat celery-exporter' not in deploy_script
    assert 'up -d backend celery-worker celery-beat' in deploy_script


def test_remote_production_deploy_removes_legacy_celery_exporter_container():
    deploy_script = (
        PROJECT_ROOT / "scripts" / "deploy_remote_production.sh"
    ).read_text(encoding="utf-8")

    assert "xihong_erp_celery_exporter" in deploy_script
    assert "Removing legacy Celery exporter container" in deploy_script
