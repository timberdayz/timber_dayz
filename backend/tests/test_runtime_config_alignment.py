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

    assert backend_env["DATABASE_URL"] == "postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp"
    assert worker_env["DATABASE_URL"] == "postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp"
