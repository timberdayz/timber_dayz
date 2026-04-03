from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
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
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="healthy\n", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(run_module.subprocess, "run", _fake_subprocess_run)

    ok = run_module.ensure_postgres_redis_docker(PROJECT_ROOT, with_celery=True)

    assert ok is True
    assert captured["calls"][0] == ["docker", "ps", "--format", "{{.Names}}"]
    assert any(cmd[:2] == ["docker", "inspect"] for cmd in captured["calls"])


def test_local_mode_does_not_reuse_unhealthy_docker_infra(monkeypatch):
    run_module = _load_run_module()
    captured = {"calls": []}
    state = {"after_compose": False}

    monkeypatch.setattr(run_module, "pre_flight_check_docker", lambda project_root: True)
    monkeypatch.setattr(run_module, "safe_print", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_module.time, "sleep", lambda *_args, **_kwargs: None)

    def _fake_subprocess_run(cmd, **kwargs):
        captured["calls"].append(cmd)
        if cmd[:3] == ["docker", "ps", "--format"]:
            return SimpleNamespace(
                returncode=0,
                stdout="xihong_erp_postgres\nxihong_erp_redis\nxihong_erp_celery_worker\n",
                stderr="",
            )
        if cmd[:2] == ["docker", "inspect"]:
            container_name = cmd[-1]
            if not state["after_compose"] and container_name == "xihong_erp_postgres":
                return SimpleNamespace(returncode=0, stdout="unhealthy\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="healthy\n", stderr="")
        if cmd[0] == "docker-compose":
            state["after_compose"] = True
            return SimpleNamespace(returncode=0, stdout="started", stderr="")
        if cmd[:3] == ["docker", "exec", "xihong_erp_postgres"]:
            return SimpleNamespace(returncode=0, stdout="1\n", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(run_module.subprocess, "run", _fake_subprocess_run)

    ok = run_module.ensure_postgres_redis_docker(PROJECT_ROOT, with_celery=True)

    assert ok is True
    assert any(cmd[:2] == ["docker", "inspect"] for cmd in captured["calls"])
    assert any(cmd[0] == "docker-compose" for cmd in captured["calls"])


def test_resolve_npm_path_prefers_matching_nvm_version(monkeypatch, tmp_path):
    run_module = _load_run_module()
    nvm_home = tmp_path / "nvm"
    wanted = nvm_home / "v24.14.0"
    other = nvm_home / "v22.9.0"
    wanted.mkdir(parents=True)
    other.mkdir(parents=True)
    (wanted / "npm.cmd").write_text("", encoding="utf-8")
    (other / "npm.cmd").write_text("", encoding="utf-8")

    monkeypatch.setattr(run_module.sys_platform, "system", lambda: "Windows")
    monkeypatch.setattr(run_module, "_read_nvmrc_version", lambda project_root: "24")
    monkeypatch.setattr(
        run_module.shutil,
        "which",
        lambda name: r"C:\legacy-node\npm.cmd" if name in {"npm", "npm.cmd"} else None,
    )
    monkeypatch.setenv("NVM_HOME", str(nvm_home))
    monkeypatch.delenv("NVM_SYMLINK", raising=False)

    npm_path = run_module._resolve_npm_path()

    assert npm_path == str(wanted / "npm.cmd")


def test_main_exits_when_backend_never_becomes_ready(monkeypatch):
    run_module = _load_run_module()
    printed: list[str] = []
    frontend_started = {"value": False}

    monkeypatch.setattr(
        run_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(
            backend_only=False,
            frontend_only=False,
            no_browser=True,
            no_celery=True,
            use_docker=False,
            collection=False,
            local=False,
        ),
    )
    monkeypatch.setattr(run_module, "print_banner", lambda: None)
    monkeypatch.setattr(run_module, "safe_print", lambda text, *args, **kwargs: printed.append(str(text)))
    monkeypatch.setattr(run_module, "check_postgresql", lambda: True)
    monkeypatch.setattr(run_module, "ensure_postgresql_dashboard_assets", lambda project_root: True)
    monkeypatch.setattr(run_module, "start_backend", lambda: SimpleNamespace())
    monkeypatch.setattr(run_module, "wait_for_service", lambda port, name, max_wait=30: False)
    monkeypatch.setattr(
        run_module,
        "start_frontend",
        lambda: frontend_started.__setitem__("value", True),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_module.main()

    assert exc_info.value.code == 1
    assert frontend_started["value"] is False
    assert not any("系统启动成功" in line for line in printed)


def test_main_exits_when_frontend_fails_to_start(monkeypatch):
    run_module = _load_run_module()
    printed: list[str] = []

    monkeypatch.setattr(
        run_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(
            backend_only=False,
            frontend_only=False,
            no_browser=True,
            no_celery=True,
            use_docker=False,
            collection=False,
            local=False,
        ),
    )
    monkeypatch.setattr(run_module, "print_banner", lambda: None)
    monkeypatch.setattr(run_module, "safe_print", lambda text, *args, **kwargs: printed.append(str(text)))
    monkeypatch.setattr(run_module, "check_postgresql", lambda: True)
    monkeypatch.setattr(run_module, "ensure_postgresql_dashboard_assets", lambda project_root: True)
    monkeypatch.setattr(run_module, "start_backend", lambda: SimpleNamespace())
    monkeypatch.setattr(run_module, "wait_for_service", lambda port, name, max_wait=30: True)
    monkeypatch.setattr(run_module, "start_frontend", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        run_module.main()

    assert exc_info.value.code == 1
    assert not any("系统启动成功" in line for line in printed)


def test_start_backend_uses_loopback_host_on_windows(monkeypatch):
    run_module = _load_run_module()
    captured = {}

    monkeypatch.setattr(run_module.sys_platform, "system", lambda: "Windows")
    monkeypatch.setattr(run_module, "safe_print", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_module, "_require_local_port_available", lambda port, name: True)

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace()

    monkeypatch.setattr(run_module.subprocess, "Popen", _fake_popen)

    run_module.start_backend()

    powershell_args = captured["cmd"]
    assert powershell_args[:2] == ["powershell", "-Command"]
    assert "--host 127.0.0.1" in powershell_args[2]


def test_choose_local_backend_port_falls_back_when_default_not_bindable(monkeypatch):
    run_module = _load_run_module()

    monkeypatch.setattr(
        run_module,
        "_can_bind_local_port",
        lambda port, host="127.0.0.1": port == 18001,
    )

    chosen_port = run_module._choose_local_backend_port(8001, fallback_ports=[18001, 18011])

    assert chosen_port == 18001
