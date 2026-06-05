import os
from pathlib import Path

from backend.utils.project_env import (
    load_project_env,
    resolve_env_profile,
    resolve_project_env_files,
)


def test_resolve_project_env_files_uses_base_and_local_files(tmp_path: Path):
    (tmp_path / ".env").write_text("A=base\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("A=local\n", encoding="utf-8")

    files = resolve_project_env_files(tmp_path)

    assert files == [tmp_path / ".env", tmp_path / ".env.local"]


def test_resolve_project_env_files_adds_collection_override_for_collection_profile(
    tmp_path: Path,
):
    (tmp_path / ".env").write_text("A=base\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("A=local\n", encoding="utf-8")
    (tmp_path / ".env.collection.local").write_text("A=collection\n", encoding="utf-8")

    files = resolve_project_env_files(tmp_path, profile="collection")

    assert files == [
        tmp_path / ".env",
        tmp_path / ".env.local",
        tmp_path / ".env.collection.local",
    ]


def test_resolve_env_profile_uses_environment_variable(monkeypatch):
    monkeypatch.setenv("XIHONG_ENV_PROFILE", "collection")

    assert resolve_env_profile() == "collection"


def test_load_project_env_applies_later_files_as_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DEPLOYMENT_ROLE", raising=False)

    (tmp_path / ".env").write_text(
        "REDIS_URL=redis://base\nDEPLOYMENT_ROLE=api\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "REDIS_URL=redis://local\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.collection.local").write_text(
        "DEPLOYMENT_ROLE=local\n",
        encoding="utf-8",
    )

    loaded_files = load_project_env(tmp_path, profile="collection")

    assert loaded_files == [
        tmp_path / ".env",
        tmp_path / ".env.local",
        tmp_path / ".env.collection.local",
    ]
    assert os.getenv("REDIS_URL") == "redis://local"
    assert os.getenv("DEPLOYMENT_ROLE") == "local"


def test_run_py_uses_project_env_loader():
    source = Path("run.py").read_text(encoding="utf-8", errors="replace")

    assert "load_project_env" in source


def test_backend_main_uses_project_env_loader():
    source = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "load_project_env" in source
