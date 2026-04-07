from pathlib import Path
import re
import importlib.util


def _load_run_module():
    spec = importlib.util.spec_from_file_location("run_module_under_test", "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_py_no_longer_accepts_with_metabase_flag():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "--with-metabase" not in text
    assert "check_metabase" not in text
    assert "Metabase" not in text


def test_run_py_does_not_keep_duplicate_entrypoint_definitions():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    for func_name in [
        "main",
        "start_backend",
        "start_frontend",
        "ensure_postgres_redis_docker",
        "_resolve_npm_path",
        "wait_for_frontend_port",
    ]:
        matches = re.findall(rf"^def {re.escape(func_name)}\(", text, flags=re.MULTILINE)
        assert len(matches) == 1, f"{func_name} should be defined exactly once"


def test_start_frontend_fails_early_when_vite_dependency_missing(tmp_path, monkeypatch):
    frontend_dir = tmp_path / "frontend"
    node_modules = frontend_dir / "node_modules"
    node_modules.mkdir(parents=True)
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")

    module = _load_run_module()
    messages = []

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr(module, "_require_local_port_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_resolve_npm_path", lambda: "C:/fake/npm.cmd")
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: object())

    result = module.start_frontend()

    assert result is None
    assert any("vite" in message.lower() for message in messages)


def test_start_backend_checks_active_backend_port(tmp_path, monkeypatch):
    module = _load_run_module()
    checked = []

    monkeypatch.setattr(module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(module, "ACTIVE_BACKEND_PORT", 18001)
    monkeypatch.setattr(module, "safe_print", lambda *_: None)
    monkeypatch.setattr(
        module,
        "_require_local_port_available",
        lambda port, service_name: checked.append((port, service_name)) or True,
    )

    class DummyProcess:
        pass

    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: DummyProcess())

    result = module.start_backend()

    assert isinstance(result, DummyProcess)
    assert checked == [(18001, "后端服务")]


def test_warn_legacy_shop_session_artifacts_reports_detected_paths(tmp_path, monkeypatch):
    module = _load_run_module()
    messages = []

    class _FakeSettings:
        DATABASE_URL = "postgresql://example"

    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr("backend.utils.config.get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        "modules.utils.sessions.legacy_shop_artifact_cleanup.collect_legacy_shop_artifacts_for_active_shops",
        lambda project_root, database_url: [
            Path(project_root) / "data" / "sessions" / "shopee" / "shop-1",
            Path(project_root) / "profiles" / "shopee" / "shop-1",
        ],
    )

    result = module.warn_legacy_shop_session_artifacts(tmp_path)

    assert result is True
    assert any("店铺级会话历史残留" in message for message in messages)
    assert any("cleanup_legacy_shop_session_artifacts.py --delete" in message for message in messages)


def test_warn_legacy_shop_session_artifacts_stays_quiet_when_no_paths(tmp_path, monkeypatch):
    module = _load_run_module()
    messages = []

    class _FakeSettings:
        DATABASE_URL = "postgresql://example"

    monkeypatch.setattr(module, "safe_print", messages.append)
    monkeypatch.setattr("backend.utils.config.get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        "modules.utils.sessions.legacy_shop_artifact_cleanup.collect_legacy_shop_artifacts_for_active_shops",
        lambda project_root, database_url: [],
    )

    result = module.warn_legacy_shop_session_artifacts(tmp_path)

    assert result is True
    assert messages == []


def test_run_py_uses_clean_docker_wait_messages():
    text = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "Docker 基础服务健康检查" in text
    assert "Docker 基础服务已就绪" in text
    assert "等待中..." in text
    assert "Docker 基础服务等待超时" in text
