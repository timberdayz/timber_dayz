"""会话存储根目录契约（Task 7：会话文件体系废除，profile 是唯一载体）。

规范依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md`` 生效版 v3。

- R1 真相源唯一：登录态只由 ``profiles/<平台>/<主账号ID>/`` 承载。
- D5：会话文件（``data/sessions/**``）**彻底废除**。
- 验收口径 E：``data/sessions/`` 不再产生新文件，目录可整体删除。

因此 ``SessionManager`` 收窄为「只解析 profile 路径」，不再暴露任何
会话文件读写接口，也不再在初始化 / 取路径时凭空创建空目录。
"""

from __future__ import annotations

from pathlib import Path


# Task 7 收窄后必须**整体消失**的会话文件接口。
_REMOVED_SESSION_APIS = (
    "save_session",
    "load_session",
    "restore_session",
    "get_session_path",
    "get_session_metadata",
    "get_session_info",
    "list_sessions",
    "cleanup_expired_sessions",
    "delete_session",
    "is_session_valid",
    "describe_storage_targets",
)

# 模块级自由函数同样必须消失（质量分 / 门禁 / 会话目录命名规则）。
_REMOVED_MODULE_HELPERS = (
    "session_quality_score",
    "session_meets_quality_gate",
    "safe_session_account_dirname",
    "_write_json_atomic",
    "_session_freshness_timestamp",
    "_extract_state_payload",
    "_cookies_from_state",
    "_origins_from_state",
    "_auth_cookie_names_for_platform",
)


def test_session_manager_no_longer_exposes_session_file_apis() -> None:
    """``SessionManager`` 不再暴露任何会话文件读写接口（D5）。"""
    from modules.utils.sessions.session_manager import SessionManager

    for name in _REMOVED_SESSION_APIS:
        assert not hasattr(SessionManager, name), (
            f"SessionManager 仍暴露会话文件接口 {name}（会话文件已废除）"
        )


def test_session_manager_no_longer_exposes_session_file_helpers() -> None:
    """模块级自由函数随会话文件体系一起消失。"""
    from modules.utils.sessions import session_manager as session_manager_module

    for name in _REMOVED_MODULE_HELPERS:
        assert not hasattr(session_manager_module, name), (
            f"session_manager 仍暴露 {name}（会话文件已废除）"
        )


def test_session_manager_initialization_does_not_create_data_sessions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """初始化 ``SessionManager`` 不得再创建 ``data/sessions`` 目录（F7-2）。"""
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    session_manager_module.SessionManager()

    assert not (repo_root / "data" / "sessions").exists()


def test_session_manager_relative_defaults_are_repo_root_anchored(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """保留的两个路径都锚定在仓库根下（不再有 ``base_path`` 形参）。"""
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()

    assert manager.profiles_path == repo_root / "data" / "session_profiles"
    assert manager.persistent_profiles_path == repo_root / "profiles"
    assert not hasattr(manager, "base_path"), "base_path 形参与属性都应随会话文件废除"


def test_get_persistent_profile_path_has_no_mkdir_side_effect(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """查 profile 路径**不得**创建空目录（B.2 #3）。

    否则「未登录账号」也会凭空多出一个空 profile 目录 → 上层
    「有没有登录态」的判断失真。
    """
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    profile_path = manager.get_persistent_profile_path("tiktok", "Tiktok 2店")

    assert profile_path == repo_root / "profiles" / "tiktok" / "Tiktok2店"
    assert not profile_path.exists(), "取 profile 路径不得产生目录副作用"


def test_get_persistent_profile_path_is_the_single_naming_rule(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """规则 B：``profiles/<平台>/<主账号ID 去空格>``（规范 v3 第 3 节）。"""
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()

    assert manager.get_persistent_profile_path("shopee", "shopee KR").name == "shopeeKR"
    assert manager.get_persistent_profile_path("tiktok", "Tiktok 1店").name == "Tiktok1店"


def test_get_profile_path_legacy_is_still_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """legacy ``data/session_profiles`` 路径解析仍保留（miaoshou_smart_login 在用）。"""
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()
    legacy_path = manager.get_profile_path("miaoshou_erp", "acc-1")

    assert legacy_path.parent.parent == repo_root / "data" / "session_profiles"
    assert legacy_path.name == "acc-1"


def test_persistent_browser_manager_downloads_root_is_repo_root_anchored(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from modules.utils import persistent_browser_manager as manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(manager_module, "REPO_ROOT", repo_root)

    path = manager_module.default_downloads_path("tiktok")

    assert path == repo_root / "downloads" / "tiktok"
