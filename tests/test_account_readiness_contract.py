"""账号就绪状态契约（纯源码，不碰数据库）。

守的是三条线：

1. **判据唯一**：「有没有人工首登」这个判定，在采集侧、CLI 体检脚本、
   巡店面板三处**必须是同一份** —— 否则会出现「面板说已首登、采集说没登录」
   这种最难查的漂移。
2. **巡店面板必须能看见问题**：被白名单排除的账号要**显式列出并写明原因**，
   就绪状态要能查到；不能继续静默跳过。
3. **前端必须轮询**：就绪状态会随人工首登变化，静态页面不刷新就永远看不到。

另外锁一条**减法**守护：就绪状态里**不得**再出现「设备画像 / machine_id 隔离」
这类判据（2026-11-14 方向修订：平台读不到 machine_id，硬件指纹同型号机器
大量重复 ⇒ 检查它们没有意义，只会让面板显示"没隔离 = 有风险"的假警报）。

再锁一条**口径对齐**守护（2026-11-14）：体检清单与巡店面板必须取**同一批**
账号（都只含启用中的）—— 停用账号不参与巡店、不参与采集，对它报「请先首登」
是假警报；但**目录撞车检查仍要保留停用账号**（profile 目录还在磁盘上）。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8）。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from fastapi.testclient import TestClient

from modules.utils.sessions.account_readiness import (
    PROFILE_COOKIE_RELATIVE_PATHS,
    build_account_readiness,
    build_profile_state,
    profile_contains_state,
)
from scripts.pwcli_account_inventory import ACCOUNT_QUERY, MainAccountRow
from scripts.pwcli_inspection_panel import PanelState, build_app


REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_HTML = REPO_ROOT / "scripts" / "pwcli_inspection_panel_static" / "index.html"


def _rows() -> list[MainAccountRow]:
    return [
        MainAccountRow("shopee", "hongxikeji:main", "hongxikeji:main", ""),
        MainAccountRow("legacy", "unsupported", "Legacy", ""),
    ]


def _write_profile(
    profiles_root: Path, platform: str, account_id: str, *, logged_in: bool
) -> Path:
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


def test_build_profile_state_only_reports_login_state() -> None:
    """就绪快照只剩「有没有首登」，不再有画像 / machine_id 判据。

    为什么锁这一条：平台读不到 ``machine_id``，硬件指纹在同型号机器上大量重复
    ⇒ 检查它们既没有意义，又会在面板上显示成"没隔离 = 有风险"的假警报。
    """
    profile_dir = Path("unused-but-must-not-be-read")
    state = build_profile_state(profile_dir)

    assert set(state.keys()) == {"profile_exists", "logged_in"}
    assert "machine_id" not in state
    assert "machine_id_isolated" not in state
    assert "has_device_profile" not in state
    assert "device" not in state


def test_build_account_readiness_uses_session_manager_naming_rule(
    tmp_path: Path,
) -> None:
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
        REPO_ROOT / "modules" / "apps" / "collection_center" / "runtime_session.py"
    ).read_text(encoding="utf-8")

    assert (
        "from modules.utils.sessions.account_readiness import profile_contains_state"
        in source
    )


def test_cli_readiness_script_and_panel_share_the_same_snapshot_builder() -> None:
    """CLI 体检脚本与巡店面板必须共用同一份判据。"""
    cli_source = (REPO_ROOT / "scripts" / "check_account_readiness.py").read_text(
        encoding="utf-8"
    )
    panel_source = (REPO_ROOT / "scripts" / "pwcli_inspection_panel.py").read_text(
        encoding="utf-8"
    )

    assert (
        "from modules.utils.sessions.account_readiness import build_profile_state"
        in cli_source
    )
    assert (
        "from modules.utils.sessions.account_readiness import build_account_readiness"
        in panel_source
    )


# ---------------------------------------------------------------------------
# 停用账号的取数口径（2026-11-14 修假警报时补上）
# ---------------------------------------------------------------------------


def _cli_function_source(name: str) -> str:
    """体检脚本里某个函数的源码 —— 避免用整文件字符串匹配做脆弱断言。"""
    import scripts.check_account_readiness as cli

    return inspect.getsource(getattr(cli, name))


def _cli_sql_of(name: str) -> str:
    """体检脚本里某个函数内的 SQL 字面量（小写）。

    只看 SQL 本身、**不看 docstring** —— 否则注释里提一句 ``enabled``
    就会被"源码里没有 enabled"这种断言误伤。
    """
    match = re.search(r'sa\.text\(\s*"""(.*?)"""', _cli_function_source(name), re.S)
    assert match is not None, "{0} 里找不到 SQL 字面量".format(name)
    return match.group(1).lower()


def test_cli_and_panel_use_the_same_enabled_filter() -> None:
    """体检清单与巡店面板必须**取同一批账号**（都只含启用中的）。

    口径漂移的后果很具体：面板只列启用账号、体检却把停用账号也拉进来，
    就会对着一个永远不会再打开的账号报「profile 目录还不存在 ⇒ 请先首登」
    —— 2026-11-14 实测的假警报（``虾皮巴西（东朗照明主体）`` 已停用却一直报警）。
    """
    panel_sql = ACCOUNT_QUERY.lower()
    cli_sql = _cli_sql_of("list_all_accounts")

    assert "enabled = true" in panel_sql, "巡店面板的取数 SQL 应当只含启用账号"
    assert "enabled = true" in cli_sql, "体检清单的取数 SQL 应当只含启用账号"


def test_cli_collision_reference_keeps_disabled_accounts() -> None:
    """**减法守护的反面**：目录撞车检查**必须**保留停用账号。

    停用账号的 profile 目录还留在磁盘上（Chromium profile 不随停用删除），
    新账号用同样的净化名建号照样会共用同一份登录态 —— 哪怕那个账号现在
    是停用的、以后重新启用也照样撞。把停用账号从参照集合里拿掉，
    等于把这个隐患藏起来。

    ⇒ 「体检清单过滤停用」与「撞车参照保留停用」是**两件事**，不能一起过滤。
    """
    collision_sql = _cli_sql_of("list_platform_accounts")

    assert (
        "enabled" not in collision_sql
    ), "撞车参照集合过滤掉了停用账号 ⇒ 新号与停用账号共用目录时不会被拦下"


def test_cli_does_not_ask_a_disabled_account_to_log_in(monkeypatch) -> None:
    """停用账号不得再报「请先首登」—— 首登 / 出口两项对它**不适用**。"""
    import scripts.check_account_readiness as cli

    monkeypatch.setattr(cli, "account_enabled", lambda *args, **kwargs: False)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("停用账号不该再查首登 / 出口 / 目录撞车")

    monkeypatch.setattr(cli, "check_login_state", _must_not_be_called)
    monkeypatch.setattr(cli, "check_proxy", _must_not_be_called)
    monkeypatch.setattr(cli, "check_profile_collision", _must_not_be_called)

    checks = cli.run_checks(
        "postgresql://unused/unused", "shopee", "虾皮巴西（东朗照明主体）"
    )
    titles = [check.title for check in checks]

    assert "已人工首登" not in titles, "停用账号不该被要求首登"
    assert "出口 IP 已配置" not in titles, "停用账号不参与采集，出口项不适用"
    assert "主账号启用状态" in titles, "应当明确说明该账号已停用"


# ---------------------------------------------------------------------------
# 巡店面板只读接口
# ---------------------------------------------------------------------------


def test_readiness_endpoint_requires_token() -> None:
    client = TestClient(
        build_app(PanelState(token="secret", account_rows_loader=_rows))
    )

    assert client.get("/api/accounts/readiness").status_code == 401
    assert client.get("/api/accounts/readiness?token=secret").status_code == 200


def test_readiness_endpoint_reports_account_state_and_skipped_accounts(
    tmp_path: Path,
) -> None:
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
    assert "logged_in" in text, "前端未渲染首登状态"
    assert "proxy_enabled" in text, "前端未渲染出口 IP 状态"


def test_panel_html_does_not_render_removed_fingerprint_badges() -> None:
    """**减法守护**：前端不得再渲染画像 / machine_id 徽标。

    这类徽标会让运维误以为"没隔离 = 有风险"，而实际上平台根本读不到
    ``machine_id``，同型号机器的硬件指纹本来就大量重复 ⇒ 显示它只会制造假警报。
    """
    text = PANEL_HTML.read_text(encoding="utf-8")

    assert "machine_id_isolated" not in text
    assert "has_device_profile" not in text
    assert "state.device" not in text


def test_panel_status_is_reset_when_browser_exits() -> None:
    """**关掉窗口就必须不再显示 OPEN**。

    真实状态由**浏览器进程**决定，不是内存里那句话。此前 watcher 检测到
    进程消失只放锁、不改 status ⇒ 面板永远显示 OPEN。
    """
    source = (REPO_ROOT / "scripts" / "pwcli_inspection_panel.py").read_text(
        encoding="utf-8"
    )

    assert 'self.statuses[key] = "idle"' in source
    watcher_at = source.index("async def _watch_browser_process")
    reset_at = source.index('self.statuses[key] = "idle"', watcher_at)
    assert reset_at > watcher_at, "状态回写必须发生在浏览器进程监控里"


def test_panel_html_renders_skipped_accounts() -> None:
    """被白名单排除的账号必须在面板上**看得见**（含原因）。"""
    text = PANEL_HTML.read_text(encoding="utf-8")

    assert "skippedSection" in text
    assert "skippedList" in text
    assert "item.reason" in text, "前端未渲染跳过原因"
