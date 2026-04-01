from __future__ import annotations

from pathlib import Path


def test_session_manager_relative_defaults_are_repo_root_anchored(monkeypatch, tmp_path: Path) -> None:
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()

    assert manager.base_path == repo_root / "data" / "sessions"
    assert manager.profiles_path == repo_root / "data" / "session_profiles"
    assert manager.persistent_profiles_path == repo_root / "profiles"


def test_session_manager_describe_storage_targets_reports_absolute_paths(monkeypatch, tmp_path: Path) -> None:
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    targets = manager.describe_storage_targets("tiktok", "Tiktok 2店")

    assert targets["session_path"] == str(repo_root / "data" / "sessions" / "tiktok" / "Tiktok 2店" / "storage_state.json")
    assert targets["persistent_profile_path"] == str(repo_root / "profiles" / "tiktok" / "Tiktok2店")


def test_persistent_browser_manager_downloads_root_is_repo_root_anchored(monkeypatch, tmp_path: Path) -> None:
    from modules.utils import persistent_browser_manager as manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(manager_module, "REPO_ROOT", repo_root)

    path = manager_module.default_downloads_path("tiktok")

    assert path == repo_root / "downloads" / "tiktok"
