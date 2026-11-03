"""会话存储根目录契约（Task 7：会话文件体系废除，profile 是唯一载体）。

规范依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md`` 生效版 v3。

- R1 真相源唯一：登录态只由 ``profiles/<平台>/<主账号ID>/`` 承载。
- D5：会话文件（``data/sessions/**``）**彻底废除**。
- 2026-11 收尾：legacy 持久化上下文目录（``data/session_profiles/**``）
  **一并废除**（最后一个使用者 ``miaoshou_smart_login`` 已切换）。
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
    """保留的路径锚定在仓库根下（不再有 ``base_path`` 形参）。"""
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()

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


def test_legacy_session_profiles_api_is_gone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """legacy ``data/session_profiles`` 解析已整体下线（2026-11 收尾）。

    最后一个使用者 ``modules/collectors/miaoshou_smart_login.py`` 已改用
    ``get_persistent_profile_path``；留着旧接口只会让人再写出一个
    **第二个**登录态目录。
    """
    from modules.utils.sessions import session_manager as session_manager_module

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(session_manager_module, "REPO_ROOT", repo_root)

    manager = session_manager_module.SessionManager()

    assert not hasattr(manager, "get_profile_path"), (
        "legacy get_profile_path 必须随 data/session_profiles 一并下线"
    )
    assert not hasattr(manager, "profiles_path"), (
        "legacy profiles_path 属性必须随 data/session_profiles 一并下线"
    )


def test_miaoshou_login_uses_the_single_profile_rule() -> None:
    """妙手登录必须落在**唯一**的 profile 规则上（``profiles/miaoshou/<主账号ID>``）。"""
    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager()

    profile_dir = manager.get_persistent_profile_path("miaoshou", "miaoshou_real_001")
    assert profile_dir.parent.name == "miaoshou"
    assert profile_dir.name == "miaoshou_real_001"

    # 源码里不得再出现 legacy 的 platform 键("miaoshou_erp")与旧接口
    # (只看**代码行**: 注释里可以解释「以前是怎么错的」)
    login_src = (
        Path(__file__).resolve().parents[2]
        / "modules"
        / "collectors"
        / "miaoshou_smart_login.py"
    ).read_text(encoding="utf-8")
    code_lines = [
        line for line in login_src.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "get_profile_path" not in code, "妙手登录不得再调用 legacy get_profile_path"
    assert 'get_persistent_profile_path("miaoshou"' in code, (
        "妙手登录必须走 get_persistent_profile_path('miaoshou', ...)"
    )


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
