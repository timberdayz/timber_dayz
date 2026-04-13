from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_snapshot_run_py_delegates_to_repo_root(monkeypatch, tmp_path):
    module = _load_module(
        "legacy_run_module_for_tests",
        PROJECT_ROOT / "build_v4271" / "run.py",
    )
    captured = {}

    legacy_script = tmp_path / "build_v4271" / "run.py"
    legacy_script.parent.mkdir(parents=True)
    legacy_script.write_text("# legacy", encoding="utf-8")
    latest_root = tmp_path
    latest_target = latest_root / "run.py"
    latest_target.write_text("# latest", encoding="utf-8")

    monkeypatch.setattr(module, "__file__", str(legacy_script))
    monkeypatch.setattr(module.sys, "argv", ["run.py", "--local", "--no-browser"])

    def _fake_run(cmd, cwd=None, check=False):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    result = module._delegate_to_latest_entrypoint_if_needed("run.py")

    assert result == 0
    assert captured["cmd"] == [
        module.sys.executable,
        str(latest_target),
        "--local",
        "--no-browser",
    ]
    assert Path(captured["cwd"]) == latest_root
    assert captured["check"] is False


def test_build_snapshot_local_run_py_delegates_to_repo_root(monkeypatch, tmp_path):
    module = _load_module(
        "legacy_local_run_module_for_tests",
        PROJECT_ROOT / "build_v4271" / "local_run.py",
    )
    captured = {}

    legacy_script = tmp_path / "build_v4271" / "local_run.py"
    legacy_script.parent.mkdir(parents=True)
    legacy_script.write_text("# legacy", encoding="utf-8")
    latest_root = tmp_path
    latest_target = latest_root / "local_run.py"
    latest_target.write_text("# latest", encoding="utf-8")

    monkeypatch.setattr(module, "__file__", str(legacy_script))
    monkeypatch.setattr(module.sys, "argv", ["local_run.py"])

    def _fake_run(cmd, cwd=None, check=False):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    result = module._delegate_to_latest_entrypoint_if_needed("local_run.py")

    assert result == 0
    assert captured["cmd"] == [
        module.sys.executable,
        str(latest_target),
    ]
    assert Path(captured["cwd"]) == latest_root
    assert captured["check"] is False


def test_root_run_py_does_not_delegate(monkeypatch):
    module = _load_module(
        "legacy_run_module_no_delegate_for_tests",
        PROJECT_ROOT / "build_v4271" / "run.py",
    )

    monkeypatch.setattr(module, "__file__", str(PROJECT_ROOT / "run.py"))

    assert module._delegate_to_latest_entrypoint_if_needed("run.py") is None
