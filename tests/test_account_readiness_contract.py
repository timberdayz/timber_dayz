"""账号就绪状态契约（纯源码，不碰数据库）。

守的是三条线：

1. **判据唯一**：「有没有人工首登」「machine_id 隔没隔离」这些判定，
   在采集侧、CLI 体检脚本、巡店面板三处**必须是同一份** ——
   否则会出现「面板说已首登、采集说没登录」这种最难查的漂移。
2. **巡店面板必须能看见问题**：被白名单排除的账号要**显式列出并写明原因**，
   就绪状态要能查到；不能继续静默跳过。
3. **前端必须轮询**：就绪状态会随人工首登变化，静态页面不刷新就永远看不到。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8 及其设备画像小节）。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from modules.utils.sessions.account_readiness import (
    PROFILE_COOKIE_RELATIVE_PATHS,
    build_account_readiness,
    build_profile_state,
    profile_contains_state,
)
from scripts.pwcli_account_inventory import MainAccountRow
from scripts.pwcli_inspection_panel import PanelState, build_app


REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_HTML = REPO_ROOT / "scripts" / "pwcli_inspection_panel_static" / "index.html"


def _rows() -> list[MainAccountRow]:
    return [
        MainAccountRow("shopee", "hongxikeji:main", "hongxikeji:main", ""),
        MainAccountRow("legacy", "unsupported", "Legacy", ""),
    ]


def _write_profile(profiles_root: Path, platform: str, account_id: str, *, logged_in: bool) -> Path:
    """按系统唯一命名规则（规则 B）造一个 profile 目录。"""
    safe_platform = "".join(c for c in platform.lower() if c.isalnum() or c in "_-")
    safe_account = "".join(c for c in account_id if c.isalnum() or c in "_-")
    profile_dir = profiles_root / safe_platform / safe_account
    profile_dir.mkdir(parents=True, exist_ok=True)
    if logged_in:
        (profile_dir / "Default" / "Network").mkdir(parents=True, exist_ok=True)
        (profile_dir / "Default" / "Network" / "Cookies").write_bytes(b"")
    return profile_dir


# ---------------------------------------------------------------------------
# 判据本体
# ---------------------------------------------------------------------------


def test_profile_contains_state_only_accepts_cookie_store(tmp_path: Path) -> None:
    """目录非空 ≠ 已登录：Chromium 启动过就会写 Default/。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert profile_contains_state(empty) is False

    started = tmp_path / "started"
    (started / "Default").mkdir(parents=True)
    assert profile_contains_state(started) is False

    for relative in PROFILE_COOKIE_RELATIVE_PATHS:
        profile = tmp_path / relative.replace("/", "_")
        (profile / relative).parent.mkdir(parents=True, exist_ok=True)
        (profile / relative).write_bytes(b"")
        assert profile_contains_state(profile) is True

    assert profile_contains_state(tmp_path / "missing") is False


def test_build_profile_state_detects_machine_id_isolation(tmp_path: Path) -> None:
    """machine_id 未隔离 ⇒ 仍与同机其它账号共享 ⇒ 平台一眼关联。"""
    from modules.utils.sessions.account_device_profile import derive_machine_id

    profile_dir = tmp_path / "shopee" / "acc"
    profile_dir.mkdir(parents=True)

    shared = build_profile_state(profile_dir, platform="shopee", account_id="acc")
    assert shared["machine_id_isolated"] is False
    assert shared["expected_machine_id"] == derive_machine_id("shopee", "acc")

    (profile_dir / "Local State").write_text(
        json.dumps({"user_experience_metrics": {"machine_id": shared["expected_machine_id"]}}),
        encoding="utf-8",
    )
    isolated = build_profile_state(profile_dir, platform="shopee", account_id="acc")
    assert isolated["machine_id_isolated"] is True
    assert isolated["machine_id"] == shared["expected_machine_id"]


def test_build_account_readiness_uses_session_manager_naming_rule(tmp_path: Path) -> None:
    """只换根目录，**不换命名规则** —— 规则仍由 SessionManager 提供。"""
    profiles_root = tmp_path / "profiles"
    _write_profile(profiles_root, "shopee", "hongxikeji:main", logged_in=True)

    payload = build_account_readiness(
        "shopee", "hongxikeji:main", profiles_root=profiles_root
    )

    assert payload["logged_in"] is True
    assert payload["profile_exists"] is True
    # 规则 B：profiles/<平台>/<主账号ID净化后>
    assert Path(payload["profile_dir"]).name == "hongxikejimain"
    assert Path(payload["profile_dir"]).parent.name == "shopee"


# ---------------------------------------------------------------------------
# 三处同源
# ---------------------------------------------------------------------------


def test_collection_side_delegates_to_shared_readiness_module() -> None:
    """采集侧的登录态判据必须**委托**共享模块，不得各写一份。"""
    source = (
        REPO_ROOT
        / "modules"
        / "apps"
        / "collection_center"
        / "runtime_session.py"
    ).read_text(encoding="utf-8")

    assert "from modules.utils.sessions.account_readiness import profile_contains_state" in source


def test_cli_readiness_script_and_panel_share_the_same_snapshot_builder() -> None:
    """CLI 体检脚本与巡店面板必须共用同一份判据。"""
    cli_source = (REPO_ROOT / "scripts" / "check_account_readiness.py").read_text(
        encoding="utf-8"
    )
    panel_source = (REPO_ROOT / "scripts" / "pwcli_inspection_panel.py").read_text(
        encoding="utf-8"
    )

    assert "from modules.utils.sessions.account_readiness import build_profile_state" in cli_source
    assert "from modules.utils.sessions.account_readiness import build_account_readiness" in panel_source


# ---------------------------------------------------------------------------
# 巡店面板只读接口
# ---------------------------------------------------------------------------


def test_readiness_endpoint_requires_token() -> None:
    client = TestClient(build_app(PanelState(token="secret", account_rows_loader=_rows)))

    assert client.get("/api/accounts/readiness").status_code == 401
    assert client.get("/api/accounts/readiness?token=secret").status_code == 200


def test_readiness_endpoint_reports_account_state_and_skipped_accounts(tmp_path: Path) -> None:
    """被白名单排除的账号必须**显式列出并带原因**，不能静默消失。"""
    client = TestClient(
        build_app(
            PanelState(
                token="secret",
                account_rows_loader=_rows,
                repo_root=tmp_path,
            )
        )
    )

    payload = client.get("/api/accounts/readiness?token=secret").json()

    assert payload["inspection_platforms"] == ["miaoshou", "shopee", "tiktok"]

    accounts = payload["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["platform"] == "shopee"
    assert accounts[0]["account_id"] == "hongxikeji:main"
    assert accounts[0]["logged_in"] is False
    assert accounts[0]["has_device_profile"] is False
    assert accounts[0]["machine_id_isolated"] is False
    assert accounts[0]["proxy_enabled"] is False

    skipped = payload["skipped"]
    assert len(skipped) == 1
    assert skipped[0]["platform"] == "legacy"
    assert skipped[0]["account_id"] == "unsupported"
    assert skipped[0]["reason"]


def test_readiness_endpoint_never_leaks_proxy_credentials(tmp_path: Path) -> None:
    """代理凭据不能进 HTTP 响应（响应会进浏览器 DOM）。"""
    rows = [
        MainAccountRow(
            "shopee",
            "acc",
            "acc",
            "",
            proxy_enabled=True,
            proxy_server="http://10.0.0.9:8080",
            proxy_username="proxy-user",
            proxy_password="proxy-pass",
        )
    ]
    client = TestClient(
        build_app(
            PanelState(
                token="secret",
                account_rows_loader=lambda: rows,
                repo_root=tmp_path,
            )
        )
    )

    body = client.get("/api/accounts/readiness?token=secret").text

    assert "proxy-pass" not in body
    assert "proxy-user" not in body
    assert "10.0.0.9" not in body


def test_accounts_endpoint_shape_is_unchanged(tmp_path: Path) -> None:
    """``/api/accounts`` 的既有响应形状不得被就绪信息污染。"""
    client = TestClient(
        build_app(
            PanelState(
                token="secret",
                account_rows_loader=_rows,
                repo_root=tmp_path,
            )
        )
    )

    body = client.get("/api/accounts?token=secret").json()

    assert body == [
        {
            "platform": "shopee",
            "display_name": "hongxikeji:main",
            "account_id": "hongxikeji:main",
            "work_tag": "shopee-hongxikeji-main-inspect",
            "status": "idle",
        }
    ]


# ---------------------------------------------------------------------------
# 前端契约
# ---------------------------------------------------------------------------


def test_panel_html_polls_readiness_and_renders_badges() -> None:
    """就绪状态会随人工首登变化 ⇒ 前端必须轮询并把徽标画出来。"""
    text = PANEL_HTML.read_text(encoding="utf-8")

    assert "/api/accounts/readiness" in text, "前端未拉取就绪状态"
    assert "setInterval" in text, "前端未做定时刷新"
    assert "POLL_INTERVAL_MS" in text
    assert "machine_id_isolated" in text, "前端未渲染 machine_id 隔离状态"
    assert "has_device_profile" in text, "前端未渲染设备画像状态"
    assert "logged_in" in text, "前端未渲染首登状态"
    assert "proxy_enabled" in text, "前端未渲染出口 IP 状态"


def test_panel_html_renders_skipped_accounts() -> None:
    """被白名单排除的账号必须在面板上**看得见**（含原因）。"""
    text = PANEL_HTML.read_text(encoding="utf-8")

    assert "skippedSection" in text
    assert "skippedList" in text
    assert "item.reason" in text, "前端未渲染跳过原因"
