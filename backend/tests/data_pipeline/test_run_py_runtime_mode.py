import importlib.util
from pathlib import Path


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
