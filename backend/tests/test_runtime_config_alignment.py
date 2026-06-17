from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_base_compose_uses_backend_api_service_name():
    compose = _read_yaml("docker-compose.yml")
    services = compose["services"]

    assert "backend-api" in services
    assert "backend" not in services


def test_dev_backend_mounts_tools_directory():
    compose = _read_yaml("docker-compose.dev.yml")
    volumes = compose["services"]["backend-api"]["volumes"]

    assert any(
        str(volume).startswith("./tools:/app/tools")
        for volume in volumes
    ), "backend dev container must mount tools into /app/tools for runtime subprocesses"


def test_dev_backend_mounts_profiles_directory_for_session_reuse():
    compose = _read_yaml("docker-compose.dev.yml")
    volumes = compose["services"]["backend-api"]["volumes"]

    assert any(
        str(volume).startswith("./profiles:/app/profiles")
        for volume in volumes
    ), "backend dev container must mount profiles into /app/profiles for session reuse"


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
    backend_env = compose["services"]["backend-api"]["environment"]
    worker_env = compose["services"]["celery-worker"]["environment"]

    assert backend_env["DATABASE_URL"] == "${DATABASE_URL}"
    assert worker_env["DATABASE_URL"] == "${DATABASE_URL}"


def test_prod_postgres_exposes_only_loopback_debug_port():
    compose = _read_yaml("docker-compose.prod.yml")
    postgres = compose["services"]["postgres"]

    assert postgres["ports"] == ["127.0.0.1:15435:5432"]


def test_prod_compose_does_not_keep_legacy_secret_fallbacks():
    compose_text = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "erp_pass_2025" not in compose_text
    assert "redis_pass_2025" not in compose_text
    assert "xihong-erp-secret-key-prod-2025" not in compose_text
    assert "xihong-erp-jwt-secret-prod-2025" not in compose_text


def test_prod_compose_forces_production_runtime_mode():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend-api"]["environment"]
    worker_env = compose["services"]["celery-worker"]["environment"]

    assert backend_env["ENVIRONMENT"] == "production"
    assert backend_env["APP_ENV"] == "production"
    assert worker_env["ENVIRONMENT"] == "production"


def test_prod_compose_allows_backend_host_for_nginx_proxy():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend-api"]["environment"]

    assert backend_env["ALLOWED_HOSTS"].endswith(",backend")


def test_dev_compose_allows_backend_host_for_nginx_proxy():
    compose = _read_yaml("docker-compose.dev.yml")
    backend_env = compose["services"]["backend-api"]["environment"]

    assert backend_env["ALLOWED_HOSTS"].endswith(",backend")


def test_dev_celery_healthcheck_does_not_depend_on_ps_binary():
    compose = _read_yaml("docker-compose.dev.yml")
    health_test = compose["services"]["celery-worker"]["healthcheck"]["test"]

    assert "ps aux" not in " ".join(str(part) for part in health_test)


def test_dev_redis_disables_aof_and_uses_temporary_broker_defaults():
    compose = _read_yaml("docker-compose.dev.yml")
    redis_service = compose["services"]["redis"]

    command = redis_service["command"]
    command_joined = " ".join(command) if isinstance(command, list) else str(command)

    assert "--appendonly no" in command_joined
    assert '--save ""' in command_joined
    assert redis_service["stop_grace_period"] == "30s"


def test_dev_compose_uses_dedicated_migrate_service_and_disables_runtime_migrations():
    compose = _read_yaml("docker-compose.dev.yml")
    services = compose["services"]

    migrate = services["migrate"]
    backend_env = services["backend-api"]["environment"]
    worker_env = services["celery-worker"]["environment"]
    beat_env = services["celery-beat"]["environment"]

    assert migrate["command"] == "alembic upgrade heads"
    assert migrate["environment"]["RUN_MIGRATIONS"] == "1"
    assert backend_env["RUN_MIGRATIONS"] == "0"
    assert worker_env["RUN_MIGRATIONS"] == "0"
    assert beat_env["RUN_MIGRATIONS"] == "0"


def test_dev_backend_healthcheck_uses_readiness_endpoint():
    compose = _read_yaml("docker-compose.dev.yml")
    health_test = compose["services"]["backend-api"]["healthcheck"]["test"]
    health_joined = " ".join(str(part) for part in health_test)

    assert "/healthz/ready" in health_joined


def test_dev_celery_healthcheck_uses_worker_readiness():
    compose = _read_yaml("docker-compose.dev.yml")
    health_test = compose["services"]["celery-worker"]["healthcheck"]["test"]
    health_joined = " ".join(str(part) for part in health_test)

    assert "inspect" in health_joined
    assert "ping" in health_joined
    assert "redis.from_url" not in health_joined


def test_dev_runtime_services_mount_sql_directory_for_refresh_pipeline():
    compose = _read_yaml("docker-compose.dev.yml")
    services = compose["services"]

    for service_name in ("backend-api", "backend-collector", "celery-worker", "celery-beat"):
        volumes = services[service_name]["volumes"]
        assert any(
            str(volume).startswith("./sql:/app/sql")
            for volume in volumes
        ), f"{service_name} must mount sql assets into /app/sql for refresh execution"


def test_dev_compose_includes_celery_beat_for_automatic_sync_scheduling():
    compose = _read_yaml("docker-compose.dev.yml")
    services = compose["services"]

    assert "celery-beat" in services
    beat = services["celery-beat"]

    assert beat["command"] == "celery -A backend.celery_app beat --loglevel=info"
    assert "dev-full" in beat["profiles"]
    assert "CELERY_BROKER_URL" in beat["environment"]
    assert "CELERY_RESULT_BACKEND" in beat["environment"]


def test_prod_compose_uses_dedicated_migrate_service_and_disables_runtime_migrations():
    compose = _read_yaml("docker-compose.prod.yml")
    services = compose["services"]

    migrate = services["migrate"]
    backend_env = services["backend-api"]["environment"]
    worker_env = services["celery-worker"]["environment"]
    beat_env = services["celery-beat"]["environment"]

    assert migrate["command"] == "alembic upgrade heads"
    assert migrate["environment"]["RUN_MIGRATIONS"] == "1"
    assert backend_env["RUN_MIGRATIONS"] == "0"
    assert worker_env["RUN_MIGRATIONS"] == "0"
    assert beat_env["RUN_MIGRATIONS"] == "0"


def test_prod_backend_role_is_api_only():
    compose = _read_yaml("docker-compose.prod.yml")
    backend_env = compose["services"]["backend-api"]["environment"]

    assert backend_env["DEPLOYMENT_ROLE"] == "api"


def test_prod_backend_healthcheck_uses_readiness_endpoint():
    compose = _read_yaml("docker-compose.prod.yml")
    health_test = compose["services"]["backend-api"]["healthcheck"]["test"]
    health_joined = " ".join(str(part) for part in health_test)

    assert "/healthz/ready" in health_joined


def test_prod_nginx_health_proxy_uses_backend_readiness_endpoint():
    nginx_conf = (PROJECT_ROOT / "nginx" / "nginx.prod.conf").read_text(encoding="utf-8")

    assert 'proxy_pass http://$backend_upstream/healthz/ready;' in nginx_conf


def test_prod_compose_injects_release_tag_into_runtime_services():
    compose = _read_yaml("docker-compose.prod.yml")
    services = compose["services"]

    assert services["backend-api"]["environment"]["APP_VERSION"] == "${IMAGE_TAG}"
    assert services["migrate"]["environment"]["APP_VERSION"] == "${IMAGE_TAG}"
    assert services["celery-worker"]["environment"]["APP_VERSION"] == "${IMAGE_TAG}"
    assert services["celery-beat"]["environment"]["APP_VERSION"] == "${IMAGE_TAG}"


def test_dev_compose_declares_explicit_backend_api_and_collector_services():
    compose = _read_yaml("docker-compose.dev.yml")
    services = compose["services"]

    assert "backend-api" in services
    assert "backend-collector" in services
    assert "backend" not in services
    assert services["backend-api"]["environment"]["DEPLOYMENT_ROLE"] == "api"
    assert services["backend-collector"]["environment"]["DEPLOYMENT_ROLE"] == "collector"


def test_dev_collector_inherits_account_encryption_key():
    compose = _read_yaml("docker-compose.dev.yml")
    collector = compose["services"]["backend-collector"]
    env = collector["environment"]

    assert env["ACCOUNT_ENCRYPTION_KEY"] == "${ACCOUNT_ENCRYPTION_KEY}"


def test_dev_collector_command_disables_reload_for_stable_worker_runtime():
    compose = _read_yaml("docker-compose.dev.yml")
    collector = compose["services"]["backend-collector"]

    command = collector["command"]
    command_joined = " ".join(command) if isinstance(command, list) else str(command)

    assert "uvicorn" in command_joined
    assert "--reload" not in command_joined


def test_prod_compose_declares_explicit_backend_api_and_collector_services():
    compose = _read_yaml("docker-compose.prod.yml")
    services = compose["services"]

    assert "backend-api" in services
    assert "backend-collector" in services
    assert "backend" not in services
    assert services["backend-collector"]["environment"]["DEPLOYMENT_ROLE"] == "collector"


def test_prod_collector_inherits_account_encryption_key():
    compose = _read_yaml("docker-compose.prod.yml")
    collector = compose["services"]["backend-collector"]
    env = collector["environment"]

    assert env["ACCOUNT_ENCRYPTION_KEY"] == "${ACCOUNT_ENCRYPTION_KEY}"


def test_cloud_overlays_target_backend_api_not_legacy_backend_service():
    for compose_name in ("docker-compose.cloud.yml", "docker-compose.cloud-4c8g.yml"):
        compose = _read_yaml(compose_name)
        services = compose["services"]

        assert "backend-api" in services
        assert "backend" not in services


def test_prod_celery_healthcheck_uses_worker_readiness():
    compose = _read_yaml("docker-compose.prod.yml")
    health_test = compose["services"]["celery-worker"]["healthcheck"]["test"]
    health_joined = " ".join(str(part) for part in health_test)

    assert "inspect" in health_joined
    assert "ping" in health_joined
    assert "redis.from_url" not in health_joined


def test_celery_app_includes_refresh_queue_task_module_and_beat_schedule():
    from backend.celery_app import celery_app

    include_modules = set(celery_app.conf.include or [])
    beat_schedule = celery_app.conf.beat_schedule or {}

    assert "backend.tasks.refresh_queue_tasks" in include_modules
    assert "process-refresh-queue-every-minute" in beat_schedule
    assert (
        beat_schedule["process-refresh-queue-every-minute"]["task"]
        == "backend.tasks.refresh_queue_tasks.process_refresh_queue_task"
    )
    assert "cleanup-stale-auto-ingest-every-5min" in beat_schedule
    assert (
        beat_schedule["cleanup-stale-auto-ingest-every-5min"]["task"]
        == "backend.tasks.scheduled_tasks.cleanup_stale_auto_ingest_tasks"
    )


def test_dev_frontend_uses_vite_port_instead_of_nginx_port():
    compose = _read_yaml("docker-compose.dev.yml")
    frontend = compose["services"]["frontend"]

    assert frontend["build"]["context"] == "."
    assert frontend["build"]["dockerfile"] == "Dockerfile.frontend"
    assert frontend["ports"] == ["${FRONTEND_PORT:-5174}:5173"]
    assert frontend["healthcheck"]["test"] == [
        "CMD",
        "wget",
        "--quiet",
        "--tries=1",
        "--spider",
        "http://localhost:5173/",
    ]


def test_cloud_overlay_increases_celery_beat_memory_limit():
    compose = _read_yaml("docker-compose.cloud.yml")
    beat_limits = compose["services"]["celery-beat"]["deploy"]["resources"]["limits"]

    assert beat_limits["memory"] == "256M"


def test_cloud_4c8g_overlay_sets_balanced_backend_and_worker_memory_limits():
    compose = _read_yaml("docker-compose.cloud-4c8g.yml")

    backend_limits = compose["services"]["backend-api"]["deploy"]["resources"]["limits"]
    worker_limits = compose["services"]["celery-worker"]["deploy"]["resources"]["limits"]

    assert backend_limits["memory"] == "1.5G"
    assert worker_limits["memory"] == "768M"


def test_remote_production_deploy_does_not_start_celery_exporter_by_default():
    deploy_script = (
        PROJECT_ROOT / "scripts" / "deploy_remote_production.sh"
    ).read_text(encoding="utf-8")

    assert 'up -d backend celery-worker celery-beat celery-exporter' not in deploy_script
    assert 'up -d --no-build backend-api celery-worker celery-beat' in deploy_script


def test_remote_production_deploy_removes_legacy_celery_exporter_container():
    deploy_script = (
        PROJECT_ROOT / "scripts" / "deploy_remote_production.sh"
    ).read_text(encoding="utf-8")

    assert "xihong_erp_celery_exporter" in deploy_script
    assert "Removing legacy Celery exporter container" in deploy_script
