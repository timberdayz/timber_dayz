"""Optional Docker proof that a release project can share the infrastructure network."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


def test_docker_integration_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_DEPLOY_DOCKER_INTEGRATION", raising=False)
    monkeypatch.setattr(
        __import__(__name__),
        "_docker_compose_command",
        lambda: (_ for _ in ()).throw(AssertionError("Docker must not be probed")),
    )

    with pytest.raises(pytest.skip.Exception, match="RUN_DEPLOY_DOCKER_INTEGRATION=1"):
        _require_docker_compose()


def _docker_compose_command() -> list[str] | None:
    if (
        shutil.which("docker")
        and subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True
        ).returncode
        == 0
    ):
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def _require_docker_compose() -> list[str]:
    if os.getenv("RUN_DEPLOY_DOCKER_INTEGRATION") != "1":
        pytest.skip(
            "set RUN_DEPLOY_DOCKER_INTEGRATION=1 to run Docker deployment integration"
        )
    command = _docker_compose_command()
    if command is None:
        pytest.skip("Docker Compose is not installed")
    if not shutil.which("docker"):
        pytest.skip("Docker CLI is not installed")
    if (
        subprocess.run(["docker", "info"], capture_output=True, text=True).returncode
        != 0
    ):
        pytest.skip("Docker daemon is not available")
    return command


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def test_release_project_run_no_deps_resolves_alias_on_external_infrastructure_network(
    tmp_path: Path,
):
    compose = _require_docker_compose()
    if (
        _run(["docker", "image", "inspect", "busybox:1.36"], cwd=tmp_path).returncode
        != 0
    ):
        pull = _run(["docker", "pull", "busybox:1.36"], cwd=tmp_path)
        if pull.returncode != 0:
            pytest.skip("busybox:1.36 cannot be pulled for Docker integration test")

    base_project = f"xihong_erp_network_test_{uuid.uuid4().hex[:8]}"
    release_project = f"xihong_erp_release_test_{uuid.uuid4().hex[:8]}"
    network_name = f"{base_project}_erp_network"
    base_compose = tmp_path / "base.compose.yml"
    release_compose = tmp_path / "release.compose.yml"
    base_compose.write_text(
        """services:
  infrastructure:
    image: busybox:1.36
    command: [\"sh\", \"-c\", \"sleep 120\"]
    networks:
      erp_network:
        aliases: [\"infrastructure-alias\"]
networks:
  erp_network: {}
""",
        encoding="utf-8",
    )
    release_compose.write_text(
        f"""services:
  probe:
    image: busybox:1.36
    networks:
      - erp_network
networks:
  erp_network:
    external: true
    name: {network_name}
""",
        encoding="utf-8",
    )

    try:
        started = _run(
            [
                *compose,
                "-p",
                base_project,
                "-f",
                str(base_compose),
                "up",
                "-d",
                "infrastructure",
            ],
            cwd=tmp_path,
        )
        assert started.returncode == 0, started.stderr

        probe = _run(
            [
                *compose,
                "-p",
                release_project,
                "-f",
                str(base_compose),
                "-f",
                str(release_compose),
                "run",
                "--rm",
                "--no-deps",
                "probe",
                "ping",
                "-c",
                "1",
                "infrastructure-alias",
            ],
            cwd=tmp_path,
        )
        assert probe.returncode == 0, probe.stderr

        release_down = _run(
            [
                *compose,
                "-p",
                release_project,
                "-f",
                str(base_compose),
                "-f",
                str(release_compose),
                "down",
                "--remove-orphans",
            ],
            cwd=tmp_path,
        )
        assert release_down.returncode == 0, release_down.stderr

        base_container = _run(
            [
                *compose,
                "-p",
                base_project,
                "-f",
                str(base_compose),
                "ps",
                "-q",
                "infrastructure",
            ],
            cwd=tmp_path,
        )
        assert base_container.returncode == 0, base_container.stderr
        container_id = base_container.stdout.strip()
        assert container_id

        running = _run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
            cwd=tmp_path,
        )
        assert running.returncode == 0, running.stderr
        assert running.stdout.strip() == "true"

        shared_network = _run(
            ["docker", "network", "inspect", network_name], cwd=tmp_path
        )
        assert shared_network.returncode == 0, shared_network.stderr
    finally:
        _run(
            [
                *compose,
                "-p",
                release_project,
                "-f",
                str(release_compose),
                "down",
                "--remove-orphans",
            ],
            cwd=tmp_path,
        )
        _run(
            [
                *compose,
                "-p",
                base_project,
                "-f",
                str(base_compose),
                "down",
                "--remove-orphans",
            ],
            cwd=tmp_path,
        )
