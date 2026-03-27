from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_run_module():
    spec = importlib.util.spec_from_file_location(
        "run_module_for_tests", PROJECT_ROOT / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_local_compose_network_does_not_pin_fixed_subnet():
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    erp_network = compose["networks"]["erp_network"]

    assert "ipam" not in erp_network


def test_local_mode_reuses_running_docker_infra(monkeypatch):
    run_module = _load_run_module()
    captured = {"calls": []}

    monkeypatch.setattr(run_module, "pre_flight_check_docker", lambda project_root: True)
    monkeypatch.setattr(run_module, "safe_print", lambda *args, **kwargs: None)

    def _fake_subprocess_run(cmd, **kwargs):
        captured["calls"].append(cmd)
        if cmd[:3] == ["docker", "ps", "--format"]:
            return SimpleNamespace(
                returncode=0,
                stdout="xihong_erp_postgres\nxihong_erp_redis\nxihong_erp_celery_worker\n",
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(run_module.subprocess, "run", _fake_subprocess_run)

    ok = run_module.ensure_postgres_redis_docker(PROJECT_ROOT, with_celery=True)

    assert ok is True
    assert captured["calls"] == [["docker", "ps", "--format", "{{.Names}}"]]
