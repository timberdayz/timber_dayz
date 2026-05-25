import importlib.util


def _load_run_module():
    spec = importlib.util.spec_from_file_location("run_module_log_hygiene", "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_start_frontend_disables_color_for_local_logs(tmp_path, monkeypatch):
    frontend_dir = tmp_path / "frontend"
    vite_dir = frontend_dir / "node_modules" / "vite"
    vite_dir.mkdir(parents=True)
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")

    module = _load_run_module()
    captured = {}

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "_pick_frontend_port", lambda preferred: 5173)
    monkeypatch.setattr(module, "_resolve_npm_path", lambda: "C:/fake/npm.cmd")
    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")

    class DummyProcess:
        pass

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return DummyProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    result = module.start_frontend()

    assert isinstance(result[0], DummyProcess)
    assert captured["env"]["NO_COLOR"] == "1"
    assert captured["env"]["CLICOLOR"] == "0"
    assert captured["env"]["FORCE_COLOR"] == "0"


def test_start_backend_disables_color_for_local_logs(tmp_path, monkeypatch):
    module = _load_run_module()
    captured = {}

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "ACTIVE_BACKEND_PORT", 18001)
    monkeypatch.setattr(module, "_require_local_port_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")

    class DummyProcess:
        pass

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return DummyProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    result = module.start_backend(runtime_mode="development", windowed=False)

    assert isinstance(result, DummyProcess)
    assert captured["env"]["NO_COLOR"] == "1"
    assert captured["env"]["CLICOLOR"] == "0"
    assert captured["env"]["FORCE_COLOR"] == "0"


def test_start_backend_registers_windows_child_process_for_parent_death_cleanup(
    tmp_path, monkeypatch
):
    module = _load_run_module()
    registered = []

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "ACTIVE_BACKEND_PORT", 18001)
    monkeypatch.setattr(module, "_require_local_port_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        module,
        "_register_process_with_windows_job",
        lambda process: registered.append(process),
    )

    class DummyProcess:
        pass

    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: DummyProcess())

    module.start_backend(runtime_mode="development", windowed=False)

    assert len(registered) == 1


def test_start_frontend_registers_windows_child_process_for_parent_death_cleanup(
    tmp_path, monkeypatch
):
    frontend_dir = tmp_path / "frontend"
    vite_dir = frontend_dir / "node_modules" / "vite"
    vite_dir.mkdir(parents=True)
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")

    module = _load_run_module()
    registered = []

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "_pick_frontend_port", lambda preferred: 5173)
    monkeypatch.setattr(module, "_resolve_npm_path", lambda: "C:/fake/npm.cmd")
    monkeypatch.setattr(module.sys_platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        module,
        "_register_process_with_windows_job",
        lambda process: registered.append(process),
    )

    class DummyProcess:
        pass

    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: DummyProcess())

    module.start_frontend()

    assert len(registered) == 1
