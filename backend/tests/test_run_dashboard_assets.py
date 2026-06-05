import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_run_module():
    module_name = "xihong_run_module_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_local_dashboard_drift_bootstraps_by_default(monkeypatch, tmp_path):
    module = _load_run_module()
    project_root = tmp_path
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "bootstrap_postgresql_dashboard.py").write_text("", encoding="utf-8")
    (scripts_dir / "verify_sql_asset_hygiene.py").write_text("", encoding="utf-8")

    calls = []

    def _fake_run(args, **kwargs):
        args = list(args)
        calls.append(args)
        if args[-2:] == ["--check", "--json"]:
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"assets_drift": True, "missing_objects": []}),
                stderr="",
            )
        if "verify_sql_asset_hygiene.py" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[-1] == "--json":
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
    monkeypatch.delenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", raising=False)

    assert module.ensure_postgresql_dashboard_assets(project_root) is True
    assert any("verify_sql_asset_hygiene.py" in call[-1] for call in calls)
    assert any(call[-1] == "--json" and "--check" not in call for call in calls)


def test_local_dashboard_drift_can_skip_bootstrap_when_disabled(monkeypatch, tmp_path):
    module = _load_run_module()
    project_root = tmp_path
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "bootstrap_postgresql_dashboard.py").write_text("", encoding="utf-8")

    calls = []

    def _fake_run(args, **kwargs):
        args = list(args)
        calls.append(args)
        if args[-2:] == ["--check", "--json"]:
            return SimpleNamespace(
                returncode=1,
                stdout=json.dumps({"assets_drift": True, "missing_objects": []}),
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess args: {args}")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
    monkeypatch.setenv("AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP", "false")

    assert module.ensure_postgresql_dashboard_assets(project_root) is True
    assert len(calls) == 1
