import importlib.util
from pathlib import Path

import pytest


def _load_run_module():
    spec = importlib.util.spec_from_file_location("run_module_runtime_mode", "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_backend_runtime_mode_prefers_local_development():
    module = _load_run_module()

    args = type(
        "Args",
        (),
        {
            "local": True,
            "use_docker": False,
            "collection": False,
            "frontend_only": False,
        },
    )()

    assert module._resolve_backend_runtime_mode(args) == "development"


def test_resolve_backend_runtime_mode_uses_collector_for_collection_docker():
    module = _load_run_module()

    args = type(
        "Args",
        (),
        {
            "local": False,
            "use_docker": True,
            "collection": True,
            "frontend_only": False,
        },
    )()

    assert module._resolve_backend_runtime_mode(args) == "collector"


def test_resolve_backend_runtime_mode_uses_production_for_standard_docker_backend():
    module = _load_run_module()

    args = type(
        "Args",
        (),
        {
            "local": False,
            "use_docker": True,
            "collection": False,
            "frontend_only": False,
        },
    )()

    assert module._resolve_backend_runtime_mode(args) == "production"


def test_run_py_mentions_runtime_mode_env():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "APP_RUNTIME_MODE" in text


def test_run_py_prefers_backend_app_main_entrypoint():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "backend.app.main:app" in text


def test_parser_rejects_conflicting_local_and_docker_modes():
    module = _load_run_module()
    parser = module.build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--local", "--use-docker"])

    assert exc_info.value.code == 2


def test_start_backend_can_disable_reload_for_windows_headless_local(monkeypatch, tmp_path):
    module = _load_run_module()
    module.ACTIVE_BACKEND_PORT = 18001

    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")
    monkeypatch.setattr(module, "_require_local_port_available", lambda port, service: True)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))

    captured = {}

    class DummyProcess:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    process = module.start_backend(runtime_mode="development", windowed=False, enable_reload=False)

    assert process is not None
    assert "--reload" not in captured["cmd"]


def test_start_celery_worker_uses_default_queues_on_windows(monkeypatch):
    module = _load_run_module()

    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")

    captured = {}

    class DummyProcess:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "safe_print", lambda *args, **kwargs: None)

    process = module.start_celery_worker()

    assert process is not None
    assert "data_sync,scheduled,data_processing" in captured["cmd"][2]


def test_cleanup_local_processes_terminates_started_children():
    module = _load_run_module()

    events = []

    class DummyProcess:
        def __init__(self, name):
            self.name = name

        def poll(self):
            return None

        def terminate(self):
            events.append(("terminate", self.name))

        def wait(self, timeout=None):
            events.append(("wait", self.name, timeout))

        def kill(self):
            events.append(("kill", self.name))

    processes = [
        ("backend", DummyProcess("backend")),
        ("frontend", DummyProcess("frontend")),
    ]

    module.cleanup_processes(processes)

    assert ("terminate", "backend") in events
    assert ("terminate", "frontend") in events
