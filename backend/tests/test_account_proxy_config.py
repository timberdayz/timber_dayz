"""账号级代理配置解析契约。

代理配置的**权威位**在 ``core.main_accounts.extra_config["proxy"]``（主账号级），
``core.shop_accounts.extra_config["proxy"]``（店铺级）仅作**回退**（历史数据仍在店铺侧）。

为什么是主账号级
----------------
业务上是「一个登录身份 = 一个设备 = 一个出口」。IP 隔离的目的就是让平台无法把这些
账号关联成「同一个出口的账号矩阵」⇒ 出口必须绑在**登录身份**上，而不是绑在某一个店上。

巡店与采集**必须用同一个来源** —— 登录时 IP 与采集时 IP 不一致，平台立刻判定「环境突变」。

解析规则集中在 ``backend/services/account_proxy_config.py``：
AccountLoaderService 与 ShopAccountLoaderService 共用同一套规则，
测试直接打在这套共享纯函数上。

规范：docs/guides/COLLECTION_SESSION_LIFECYCLE.md P1~P4 与 R8.4
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.account_loader_service import AccountLoaderService
from backend.services.account_proxy_config import (
    extract_proxy_config,
    mask_proxy_server,
    resolve_account_proxy,
    split_proxy_credentials,
)

# 遗留地区池链路的标识符（含 fallback_to_direct 静默直连）。
# N6：补上 ProxyConfigManager —— 早期只按小写模块名判定，
# ``from ... import ProxyConfigManager`` 这种写法检测不到。
_FORBIDDEN_PROXY_CHAIN_NAMES = frozenset(
    {
        "proxy_config_manager",
        "ProxyConfigManager",
        "get_playwright_proxy_config",
        "get_account_proxy",
        "fallback_to_direct",
    }
)

# 代理链路上真正会写 proxy 的文件（不只解析模块）。
# N6：补上指纹层与浏览器配置层 —— 它们同样会把 proxy 写进 context options。
_PROXY_CHAIN_SCANNED_FILES = (
    "backend/services/account_proxy_config.py",
    "backend/domains/collection/routers/collection_tasks.py",
    "modules/apps/collection_center/executor_v2.py",
    "modules/apps/collection_center/runtime_session.py",
    "modules/utils/sessions/device_fingerprint.py",
    "modules/apps/collection_center/browser_config_helper.py",
)


def _make_service() -> AccountLoaderService:
    """构造一个不需要真实密钥的 loader（测试里不需要真的解密）。"""
    service = AccountLoaderService()
    service._decrypt_password = lambda encrypted: "plain-password"
    return service


def _make_main_account(extra_config=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        platform="shopee",
        main_account_id="shopee KR",
        username="demo-user",
        password_encrypted="enc",
        login_url="https://example.test/login",
        email="demo@example.test",
        phone="",
        enabled=True,
        notes="",
        extra_config=extra_config,
    )


def _make_shop_account(extra_config) -> SimpleNamespace:
    return SimpleNamespace(
        id=2,
        platform="shopee",
        shop_account_id="shopee_sg_x",
        main_account_id="shopee KR",
        store_name="demo.sg",
        platform_shop_id="",
        platform_shop_id_status="none",
        shop_region="SG",
        shop_type="local",
        enabled=True,
        notes="",
        extra_config=extra_config,
    )


def test_account_loader_exposes_proxy_config():
    """P1：代理配置挂账号上，从 extra_config 透出到账号 dict。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account(
            {
                "proxy": {
                    "enabled": True,
                    "server": "http://10.0.0.9:8080",
                    "region": "sg",
                }
            }
        ),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_enabled"] is True
    assert account["proxy_server"] == "http://10.0.0.9:8080"
    assert account["proxy_region"] == "sg"


def test_main_account_level_proxy_is_used():
    """R8.4：代理权威位在**主账号**级 —— 出口绑在登录身份上。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(
            {
                "proxy": {
                    "enabled": True,
                    "server": "http://10.0.0.1:8080",
                    "region": "sg",
                }
            }
        ),
        _make_shop_account(None),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_enabled"] is True
    assert account["proxy_server"] == "http://10.0.0.1:8080"
    assert account["proxy_region"] == "sg"


def test_main_account_level_proxy_takes_priority_over_shop_level():
    """两级都配了 ⇒ **主账号级赢**（一个登录身份只能有一个出口）。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(
            {"proxy": {"enabled": True, "server": "http://10.0.0.1:8080"}}
        ),
        _make_shop_account(
            {"proxy": {"enabled": True, "server": "http://10.0.0.9:8080"}}
        ),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_server"] == "http://10.0.0.1:8080"


def test_shop_level_proxy_is_used_as_fallback():
    """主账号级没配 ⇒ 回退到店铺级（历史数据仍在店铺侧）。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(None),
        _make_shop_account(
            {"proxy": {"enabled": True, "server": "http://10.0.0.9:8080"}}
        ),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_server"] == "http://10.0.0.9:8080"


def test_account_loader_tolerates_missing_proxy_config():
    """代理配置缺失（extra_config 为 None / 没有 proxy 子字典）时安全兜底。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account(None),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_enabled"] is False
    assert account["proxy_server"] == ""
    assert account["proxy_region"] == ""
    assert account["proxy_required"] is False


def test_account_loader_keeps_legacy_proxy_required_flag():
    """历史遗留布尔标记仍然生效，且启用代理时 proxy_required 跟着为真。"""
    service = _make_service()

    legacy_account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account({"legacy_proxy_required": True}),
        {"orders": True},
    )
    assert legacy_account is not None
    assert legacy_account["proxy_required"] is True
    assert legacy_account["proxy_enabled"] is False

    enabled_account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account({"proxy": {"enabled": True, "server": "http://10.0.0.9:8080"}}),
        {"orders": True},
    )
    assert enabled_account is not None
    assert enabled_account["proxy_required"] is True
    assert enabled_account["proxy_server"] == "http://10.0.0.9:8080"
    assert enabled_account["proxy_region"] == ""


@pytest.mark.parametrize(
    "extra_config, expected",
    [
        (None, (False, "", "")),
        ({}, (False, "", "")),
        ({"proxy": None}, (False, "", "")),
        ({"proxy": "http://h:1"}, (False, "", "")),  # proxy 不是 dict
        ({"proxy": ["a"]}, (False, "", "")),
        ({"proxy": {"enabled": True, "server": None}}, (True, "", "")),
        ({"proxy": {"enabled": True, "region": "   "}}, (True, "", "")),
        ({"proxy": {"enabled": True, "server": " http://h:1 "}}, (True, "http://h:1", "")),
        ({"proxy": {"enabled": "false", "server": "http://h:1"}}, (False, "http://h:1", "")),
        ({"proxy": {"enabled": "true"}}, (True, "", "")),
        ({"proxy": {"enabled": False, "server": "http://h:1"}}, (False, "http://h:1", "")),
        ({"proxy": {"server": {"host": "h"}}}, (False, "", "")),  # 非标量 server
        # extra_config 本身类型不对：本函数必须安全兜底、不抛异常
        ("not-a-dict", (False, "", "")),
        (["not-a-dict"], (False, "", "")),
        # enabled 为数字
        ({"proxy": {"enabled": 1, "server": "http://h:1"}}, (True, "http://h:1", "")),
        ({"proxy": {"enabled": 0}}, (False, "", "")),
        # 数字标量转字符串（端口号写成数字时）
        ({"proxy": {"enabled": True, "server": 8080}}, (True, "8080", "")),
    ],
)
def test_extract_proxy_config_boundaries(extra_config, expected):
    """解析规则边界表：Task 2 会复用同一套解析，这里必须钉死。"""
    result = extract_proxy_config(extra_config)
    assert (
        result["proxy_enabled"],
        result["proxy_server"],
        result["proxy_region"],
    ) == expected


def test_split_proxy_credentials_extracts_userinfo():
    """带凭据的代理串必须拆成 Playwright 的 server/username/password。"""
    assert split_proxy_credentials("http://user:pass@h:8080") == {
        "server": "http://h:8080",
        "username": "user",
        "password": "pass",
    }
    assert split_proxy_credentials("http://h:8080") == {"server": "http://h:8080"}
    assert split_proxy_credentials("") == {}


def test_split_proxy_credentials_normalizes_missing_scheme():
    """C3：代理串必须带 scheme（本仓约定见 proxy_config_manager.py:61）。

    Playwright 的 python 绑定不校验 proxy["server"]，畸形值只会在导航期报
    ERR_PROXY_CONNECTION_FAILED，看不出是配置写错 —— 所以缺 scheme 必须在这里补。
    """
    assert split_proxy_credentials("user:pass@h:8080") == {
        "server": "http://h:8080",
        "username": "user",
        "password": "pass",
    }
    assert split_proxy_credentials("h:8080") == {"server": "http://h:8080"}
    # 已有 scheme 的原样保留（socks5 等非 http 协议不能被改写）
    assert split_proxy_credentials("socks5://h:1080") == {"server": "socks5://h:1080"}


def test_mask_proxy_server_drops_credentials():
    """诊断字段用：凭据必须被抹掉（规范 §8 session_proxy 脱敏）。"""
    assert mask_proxy_server("http://user:pass@h:8080") == "http://h:8080"
    assert "pass" not in mask_proxy_server("http://user:pass@h:8080")


# ---------------------------------------------------------------------------
# Task 2：代理链路打通（C1~C5 + 断点①~⑥）
# ---------------------------------------------------------------------------


def test_proxy_reaches_context_options():
    """代理必须进入 Playwright context options（白名单不能丢）。"""
    from modules.apps.collection_center.runtime_session import (
        _build_playwright_context_options_from_fingerprint,
    )

    opts = _build_playwright_context_options_from_fingerprint(
        {"proxy": {"server": "http://10.0.0.9:8080"}}
    )
    assert opts["proxy"]["server"] == "http://10.0.0.9:8080"


def test_proxy_reaches_executor_context_options():
    """执行器侧的 context options 白名单同样不能丢 proxy（两处 allowed 都要改）。"""
    from modules.apps.collection_center.executor_v2 import (
        _build_playwright_context_options_from_fingerprint,
    )

    opts = _build_playwright_context_options_from_fingerprint(
        {"proxy": {"server": "http://10.0.0.9:8080"}}
    )
    assert opts["proxy"]["server"] == "http://10.0.0.9:8080"


def test_extract_proxy_config_exposes_standalone_credentials():
    """C4：独立的 username/password 形态必须透出，不能被静默丢弃。"""
    result = extract_proxy_config(
        {
            "proxy": {
                "enabled": True,
                "server": "http://h:8080",
                "username": "u",
                "password": "p",
            }
        }
    )
    assert result["proxy_enabled"] is True
    assert result["proxy_server"] == "http://h:8080"
    assert result["proxy_username"] == "u"
    assert result["proxy_password"] == "p"


def test_normalize_proxy_server_handles_empty_input():
    """空输入必须安全兜底（不能变成 "http://" 这种畸形代理串）。"""
    from backend.services.account_proxy_config import _normalize_proxy_server

    assert _normalize_proxy_server("") == ""
    assert _normalize_proxy_server("   ") == ""


def test_resolve_account_proxy_uses_only_account_config():
    """C1：账号自有代理优先，遗留地区池的产物不得混进来。"""
    resolved = resolve_account_proxy(
        {
            "account_id": "shopee_sg_x",
            "proxy_enabled": True,
            "proxy_server": "http://10.0.0.9:8080",
            "proxy_region": "sg",
        }
    )
    assert resolved == {"server": "http://10.0.0.9:8080"}


def test_resolve_account_proxy_ignores_legacy_region_pool_signals():
    """C1：遗留地区池信号（proxy_required / 地区池 key）不得影响账号自有代理。

    这条钉的是**行为**：即使账号 dict 里带着遗留地区池的字段，
    解析结果也只能来自账号自己的 proxy_server。
    """
    resolved = resolve_account_proxy(
        {
            "account_id": "shopee_sg_x",
            "proxy_required": True,
            "proxy_region": "singapore",
            "proxy_enabled": True,
            "proxy_server": "http://10.0.0.9:8080",
        }
    )
    assert resolved == {"server": "http://10.0.0.9:8080"}
    assert "singapore" not in str(resolved)


def _collect_referenced_names(source: str) -> set[str]:
    """收集源码里引用到的标识符（含 import 的模块路径分段）。

    N6：早期实现只收 ``ast.Name`` / ``ast.Attribute`` / ``alias.name``，
    **从不收** ``ast.ImportFrom.module`` —— 于是
    ``from modules.utils.proxy_config_manager import ProxyConfigManager``
    （本仓 ``modules/collectors/shopee_collector.py:47`` 的写法）检测不到。
    这里把 import 的模块路径也按 ``.`` 拆开收集，模块路径与被导入名都算命中。
    """
    import ast

    tree = ast.parse(source)
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                referenced.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                referenced.update(node.module.split("."))
            for alias in node.names:
                referenced.update(alias.name.split("."))
    return referenced


def test_account_proxy_chain_never_references_legacy_direct_fallback():
    """C1/C2：代理链路不得引用遗留地区池链路。

    遗留链路带 ``fallback_to_direct``（代理失败静默直连），且只按
    account_id + 地区池选代理 —— 自有代理场景引用它就是"一账号两个 IP"。

    这条扫描的是**整条代理链路**上真正会写 proxy 的文件（不只解析模块），
    只要有人重新 import/调用遗留链路就会红。
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    for relative_path in _PROXY_CHAIN_SCANNED_FILES:
        source = (repo_root / relative_path).read_text(
            encoding="utf-8", errors="replace"
        )
        leaked = _collect_referenced_names(source) & set(_FORBIDDEN_PROXY_CHAIN_NAMES)
        assert not leaked, f"{relative_path} 引用了遗留代理链路: {sorted(leaked)}"


def test_legacy_proxy_chain_guard_detects_import_from_module_path():
    """N6：``from ... import ProxyConfigManager`` 形式也必须被守卫检出。

    早期实现只收 ``alias.name``，漏掉 ``ImportFrom.module`` ——
    于是本仓 ``modules/collectors/shopee_collector.py:47`` 的写法检测不到。
    """
    from_import = _collect_referenced_names(
        "from modules.utils.proxy_config_manager import ProxyConfigManager\n"
    )
    assert "ProxyConfigManager" in from_import
    assert "proxy_config_manager" in from_import

    plain_import = _collect_referenced_names(
        "import modules.utils.proxy_config_manager\n"
    )
    assert "proxy_config_manager" in plain_import

    # 早前就能检出的形态不得退化
    assert "get_account_proxy" in _collect_referenced_names(
        "from modules.utils.proxy_config_manager import get_account_proxy\n"
    )
    # 属性访问形态同样要能检出
    assert "get_playwright_proxy_config" in _collect_referenced_names(
        "manager.get_playwright_proxy_config(account)\n"
    )



@pytest.mark.parametrize(
    "account",
    [
        {"proxy_enabled": False, "proxy_server": "http://10.0.0.9:8080"},
        {"proxy_enabled": True, "proxy_server": ""},
        {"proxy_enabled": True},
        {},
        None,
    ],
)
def test_resolve_account_proxy_returns_none_without_usable_account_proxy(account):
    """C2：没有可用自有代理时返回 None（不造假代理，也不静默换一条链路）。"""
    assert resolve_account_proxy(account) is None


def test_resolve_account_proxy_prefers_standalone_credentials():
    """C4：独立字段优先于 URL 内嵌凭据。"""
    resolved = resolve_account_proxy(
        {
            "proxy_enabled": True,
            "proxy_server": "http://embedded:embeddedpass@h:8080",
            "proxy_username": "standalone",
            "proxy_password": "standalonepass",
        }
    )
    assert resolved == {
        "server": "http://h:8080",
        "username": "standalone",
        "password": "standalonepass",
    }


def test_resolve_account_proxy_falls_back_to_embedded_credentials():
    """C4：没有独立字段时回退到 URL 内嵌凭据。"""
    resolved = resolve_account_proxy(
        {
            "proxy_enabled": True,
            "proxy_server": "http://embedded:embeddedpass@h:8080",
        }
    )
    assert resolved == {
        "server": "http://h:8080",
        "username": "embedded",
        "password": "embeddedpass",
    }


def test_account_loader_proxy_required_is_false_when_enabled_flag_is_false():
    """Minor 4：enabled="false" 时 proxy_required 必须是 False（字符串真值陷阱）。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account(
            {"proxy": {"enabled": "false", "server": "http://10.0.0.9:8080"}}
        ),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_enabled"] is False
    assert account["proxy_required"] is False


def test_account_loader_exposes_standalone_credentials():
    """C4：独立凭据形态要一路透出到账号 dict。"""
    service = _make_service()

    account = service._build_account_dict(
        _make_main_account(),
        _make_shop_account(
            {
                "proxy": {
                    "enabled": True,
                    "server": "http://10.0.0.9:8080",
                    "username": "u",
                    "password": "p",
                }
            }
        ),
        {"orders": True},
    )

    assert account is not None
    assert account["proxy_username"] == "u"
    assert account["proxy_password"] == "p"


def test_shop_account_loader_exposes_proxy_config(monkeypatch):
    """主运行时路径（shop loader）的 compat_account 也必须带 proxy 键。"""
    from backend.services import shop_account_loader_service as shop_module

    monkeypatch.setattr(
        shop_module,
        "get_encryption_service",
        lambda: SimpleNamespace(decrypt_password=lambda encrypted: "plain-password"),
    )
    service = shop_module.ShopAccountLoaderService()

    payload = service._build_payload(
        _make_main_account(),
        _make_shop_account(
            {
                "proxy": {
                    "enabled": True,
                    "server": "http://10.0.0.9:8080",
                    "region": "sg",
                    "username": "u",
                    "password": "p",
                }
            }
        ),
        {"orders": True},
    )

    compat = payload["compat_account"]
    assert compat["proxy_enabled"] is True
    assert compat["proxy_server"] == "http://10.0.0.9:8080"
    assert compat["proxy_region"] == "sg"
    assert compat["proxy_username"] == "u"
    assert compat["proxy_password"] == "p"


def test_mask_proxy_server_scrubs_standalone_credentials():
    """C5：独立形态的凭据也不得出现在诊断字段里。"""
    masked = mask_proxy_server(
        "http://10.0.0.9:8080",
        username="secret-user",
        password="secret-pass",
    )
    assert masked == "http://10.0.0.9:8080"
    assert "secret-user" not in masked
    assert "secret-pass" not in masked


async def test_executor_open_runtime_bundle_forwards_account_proxy(monkeypatch):
    """断点①：代理必须一路传到 runtime bundle（浏览器真正使用的入口）。"""
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    persistent_open = AsyncMock(return_value="persistent-bundle")
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.open_persistent_runtime_bundle",
        persistent_open,
    )

    executor = CollectionExecutorV2()
    await executor._open_runtime_bundle(
        session_runtime_mode="persistent_profile",
        browser=object(),
        browser_type=object(),
        platform="shopee",
        session_owner_id="main-1",
        runtime_account={"login_url": "https://seller.shopee.cn"},
        storage_state=None,
        launch_kwargs={"headless": True},
        proxy={"server": "http://10.0.0.9:8080"},
    )

    assert persistent_open.await_args.kwargs["proxy"] == {
        "server": "http://10.0.0.9:8080"
    }


async def test_persistent_context_receives_account_proxy(monkeypatch, tmp_path):
    """断点⑤：profile 模式必须把代理传给 launch_persistent_context。"""
    from modules.apps.collection_center import runtime_session

    profile_path = tmp_path / "profiles" / "shopee" / "main-1"
    profile_path.mkdir(parents=True)
    captured: dict[str, object] = {}

    class _FakeContext:
        pages = [object()]

        async def add_init_script(self, script: str) -> None:
            return None

    class _FakeBrowserType:
        async def launch_persistent_context(self, **kwargs):
            captured.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: profile_path,
    )
    # 模拟指纹链路已经把 proxy 带进 context options 的真实情况：
    # launch_persistent_context 的 proxy 与 context 级 proxy 语义不同，不能重复传同一个 key。
    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        AsyncMock(
            return_value={
                "locale": "zh-CN",
                "viewport": {"width": 1920, "height": 1080},
                "accept_downloads": True,
                "proxy": {"server": "http://10.0.0.9:8080"},
            }
        ),
    )

    await runtime_session.open_persistent_runtime_bundle(
        browser_type=_FakeBrowserType(),
        platform="shopee",
        session_owner_id="main-1",
        account={"login_url": "https://seller.shopee.cn"},
        launch_kwargs={"headless": True},
        proxy={"server": "http://10.0.0.9:8080"},
    )

    assert captured["proxy"] == {"server": "http://10.0.0.9:8080"}


# ---------------------------------------------------------------------------
# 代码质量评审修复项（P0-1 / P1-2 / P1-3 / P0-4）
# ---------------------------------------------------------------------------

_FAKE_FINGERPRINT = {
    "user_agent": "Fake-UA",
    "viewport": {"width": 1920, "height": 1080},
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai",
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
    "color_scheme": "light",
    "reduced_motion": "no-preference",
    "forced_colors": "none",
    "extra_http_headers": {"Accept-Language": "zh-CN"},
    "permissions": {},
}


@pytest.mark.parametrize(
    "raw",
    [
        "http://user:pass",
        "https://user:pass",
        "user:pass",
        "socks5://user:pass",
        "http://user:pass:8080",
    ],
)
def test_split_proxy_credentials_never_keeps_credentials_in_server(raw):
    """P0-1：没有 "@" 的 user:pass 形态也必须按 userinfo 拆开。

    否则明文密码会留在 server 里：既进日志（mask 直接透出），也会被当成
    代理地址下发到 Playwright。
    """
    result = split_proxy_credentials(raw)
    server = str(result.get("server") or "")
    assert "user" not in server
    assert "pass" not in server
    assert result["username"] == "user"
    assert result["password"].startswith("pass")


@pytest.mark.parametrize(
    "raw",
    ["http://user:pass", "user:pass", "socks5://user:pass"],
)
def test_mask_proxy_server_drops_credentials_without_at_sign(raw):
    """P0-1：脱敏输出不得包含明文凭据。"""
    masked = mask_proxy_server(raw)
    assert "user" not in masked
    assert "pass" not in masked


def test_split_proxy_credentials_keeps_ipv6_literal():
    """IPv6 字面量不能被误判成 userinfo（否则代理地址会被拆坏）。"""
    assert split_proxy_credentials("[::1]:8080") == {"server": "http://[::1]:8080"}
    assert split_proxy_credentials("http://[::1]:8080") == {
        "server": "http://[::1]:8080"
    }
    assert split_proxy_credentials("http://u:p@[::1]:8080") == {
        "server": "http://[::1]:8080",
        "username": "u",
        "password": "p",
    }
    # IPv6 账号必须能正常解析出代理（主机判定也要认 IPv6 字面量）
    assert resolve_account_proxy(
        {"proxy_enabled": True, "proxy_server": "http://[::1]:8080"}
    ) == {"server": "http://[::1]:8080"}
    assert mask_proxy_server("http://[::1]:8080") == "http://[::1]:8080"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("socks5://h:1080", {"server": "socks5://h:1080"}),
        ("socks5h://h:1080", {"server": "socks5h://h:1080"}),
        (
            "socks5://u:p@h:1080",
            {"server": "socks5://h:1080", "username": "u", "password": "p"},
        ),
        (
            "socks5h://u:p@h:1080",
            {"server": "socks5h://h:1080", "username": "u", "password": "p"},
        ),
    ],
)
def test_split_proxy_credentials_keeps_non_http_scheme(raw, expected):
    """socks5/socks5h 不得被改写成 http。"""
    assert split_proxy_credentials(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 空端口：主机还在，缺的是端口 —— 不能被判成 userinfo
        ("http://h:", {"server": "http://h:"}),
        # 带路径：端口位是 "8080"，不是 "8080/path" —— 不能被判成 userinfo
        ("http://host:8080/path", {"server": "http://host:8080/path"}),
        # 裸 IPv6：不是 userinfo（主机是在的）
        ("http://::1:8080", {"server": "http://::1:8080"}),
        # 括号 IPv6：已经正确的形态，不能被破坏
        ("http://[::1]:8080", {"server": "http://[::1]:8080"}),
        (
            "http://u:p@[::1]:8080",
            {"server": "http://[::1]:8080", "username": "u", "password": "p"},
        ),
        # socks5：已经正确的形态，不能被破坏
        ("socks5://h:1080", {"server": "socks5://h:1080"}),
        # 空 userinfo：不得产出空的 username/password 键
        ("http://@h:8080", {"server": "http://h:8080"}),
    ],
)
def test_split_proxy_credentials_handles_malformed_proxy_strings(raw, expected):
    """N1/N2/N4：畸形代理串的处理必须一致，且不能误伤已经正确的形态。

    早期实现把"空端口""带路径""裸 IPv6"一律当成 userinfo → server 被剥成
    "http://"，于是代理串里的主机（其实在）被误报成"缺少代理主机"。
    """
    assert split_proxy_credentials(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "http://u:p@h:8080",
            {"server": "http://h:8080", "username": "u", "password": "p"},
        ),
        # 只有用户名：不得产出空 password 键
        ("http://u:@h:8080", {"server": "http://h:8080", "username": "u"}),
        # 只有密码：不得产出空 username 键
        ("http://:p@h:8080", {"server": "http://h:8080", "password": "p"}),
        # 空 userinfo：两个键都不产出
        ("http://@h:8080", {"server": "http://h:8080"}),
    ],
)
def test_split_proxy_credentials_never_emits_empty_credential_keys(raw, expected):
    """N2：空凭据不得产出空的 username/password 键。

    空键带给 Playwright 会被当成"有用户名无密码"，需要认证的代理直接 407。
    """
    assert split_proxy_credentials(raw) == expected


def test_split_proxy_credentials_keeps_lettered_userinfo_out_of_bare_ipv6_rule():
    """N1：裸 IPv6 判定不能误伤带字母的凭据串。

    ``user::pass`` 含 ``::`` 但不是 IPv6 字面量 —— 那种串拆不出主机，
    凭据必须从 server 里剥掉（否则明文密码会留在 server 里）。
    """
    result = split_proxy_credentials("http://user::pass")
    assert result["server"] == "http://"
    assert result["username"] == "user"
    assert result["password"] == ":pass"


def test_resolve_account_proxy_keeps_host_of_malformed_but_parseable_strings():
    """N1/N2：主机还在的畸形串不得被误报成"缺少代理主机"。

    早期实现把这些串判成 userinfo → server 变成 "http://" → 抛出的报错
    指向"缺少主机"，但主机其实在，提示会误导运维去查错方向。
    """
    assert resolve_account_proxy(
        {"proxy_enabled": True, "proxy_server": "http://h:"}
    ) == {"server": "http://h:"}
    assert resolve_account_proxy(
        {"proxy_enabled": True, "proxy_server": "http://host:8080/path"}
    ) == {"server": "http://host:8080/path"}
    assert resolve_account_proxy(
        {"proxy_enabled": True, "proxy_server": "http://::1:8080"}
    ) == {"server": "http://::1:8080"}


def test_mask_proxy_server_never_leaks_credentials_of_malformed_strings():
    """N2：畸形串的脱敏结果同样不得带明文凭据。"""
    assert mask_proxy_server("http://@h:8080") == "http://h:8080"
    assert mask_proxy_server("http://u:@h:8080") == "http://h:8080"
    assert "user" not in mask_proxy_server("http://user::pass")


def test_mask_proxy_server_normalizes_missing_scheme():
    """脱敏结果同样要带 scheme（与 split 的归一口径一致）。"""
    assert mask_proxy_server("h:8080") == "http://h:8080"
    assert mask_proxy_server("user:pass@h:8080") == "http://h:8080"
    # 没有端口的普通主机：脱敏后必须原样保留
    assert mask_proxy_server("http://proxy.example.com") == "http://proxy.example.com"


def test_mask_proxy_server_never_damages_host_port_or_scheme():
    """P1-2：独立凭据不得用字符串替换去抹。

    早期实现用 replace(secret) 抹独立凭据，会把 host 段/端口/scheme 一起抹掉
    （username='h' -> '***ttp://***:8080'）。独立凭据本来就不在 server 里，
    正确语义是"输出只体现 server"。
    """
    assert mask_proxy_server("http://h:8080", username="h") == "http://h:8080"
    assert mask_proxy_server("http://h:8080", password="8080") == "http://h:8080"
    assert mask_proxy_server("http://h:8080", password="http") == "http://h:8080"


def test_extract_proxy_config_keeps_username_without_password():
    """只有 username 没有 password 也是合法形态。"""
    result = extract_proxy_config(
        {"proxy": {"enabled": True, "server": "http://h:8080", "username": "u"}}
    )
    assert result["proxy_username"] == "u"
    assert result["proxy_password"] == ""


def test_resolve_account_proxy_supports_username_without_password():
    resolved = resolve_account_proxy(
        {
            "proxy_enabled": True,
            "proxy_server": "http://h:8080",
            "proxy_username": "u",
        }
    )
    assert resolved == {"server": "http://h:8080", "username": "u"}


def test_resolve_account_proxy_rejects_string_false_enabled_flag():
    """resolve 层同样要处理字符串真值陷阱（loader 层之外也可能是裸 dict）。"""
    assert (
        resolve_account_proxy(
            {"proxy_enabled": "false", "proxy_server": "http://h:8080"}
        )
        is None
    )


def test_resolve_account_proxy_fails_loudly_when_server_has_no_host():
    """P0-1/C2：拆不出主机部分时必须显式失败，绝不静默直连。

    静默直连会让账号从宿主 IP 出现，IP 隔离形同虚设（C2）。
    """
    with pytest.raises(ValueError) as excinfo:
        resolve_account_proxy(
            {
                "account_id": "acc-leak",
                "proxy_enabled": True,
                "proxy_server": "http://user:supersecret",
            }
        )
    message = str(excinfo.value)
    assert "supersecret" not in message
    assert "user" not in message


def test_strip_account_proxy_credentials_removes_all_credentials():
    """P0-4：组件 config 不能带明文代理密码。"""
    from backend.services.account_proxy_config import strip_account_proxy_credentials

    stripped = strip_account_proxy_credentials(
        {
            "account_id": "shopee_sg_x",
            "proxy_enabled": True,
            "proxy_server": "http://embedded:embeddedpass@h:8080",
            "proxy_username": "u",
            "proxy_password": "p",
        }
    )
    assert "proxy_username" not in stripped
    assert "proxy_password" not in stripped
    assert stripped["proxy_server"] == "http://h:8080"
    assert stripped["proxy_enabled"] is True
    # 原字典不能被就地改掉（调用方还要用它解析代理）
    source = {
        "proxy_server": "http://embedded:embeddedpass@h:8080",
        "proxy_username": "u",
        "proxy_password": "p",
    }
    strip_account_proxy_credentials(source)
    assert source["proxy_username"] == "u"
    # 没有代理配置的账号：原样返回
    assert strip_account_proxy_credentials({"account_id": "x"}) == {
        "account_id": "x"
    }
    # 拆不出 server 的畸形串：不得把凭据留在 proxy_server 里
    malformed = strip_account_proxy_credentials({"proxy_server": "user:pass"})
    assert "proxy_server" not in malformed


def test_strip_account_proxy_credentials_drops_proxy_server_without_host():
    """N4：拆不出主机就删键 —— 与 "user:pass" 口径一致。

    早期实现把 "http://user:pass" 剥成 "http://" 这种垃圾代理地址留在
    组件 config 里，而 "user:pass" 会删键 —— 同一件事两种语义。
    """
    from backend.services.account_proxy_config import strip_account_proxy_credentials

    assert "proxy_server" not in strip_account_proxy_credentials(
        {"proxy_server": "http://user:pass"}
    )
    assert "proxy_server" not in strip_account_proxy_credentials(
        {"proxy_server": "user:pass"}
    )
    # 主机还在的串：保留剥掉凭据后的地址
    assert strip_account_proxy_credentials(
        {"proxy_server": "http://embedded:embeddedpass@h:8080"}
    )["proxy_server"] == "http://h:8080"
    assert strip_account_proxy_credentials(
        {"proxy_server": "http://h:"}
    )["proxy_server"] == "http://h:"


def test_runtime_account_drops_proxy_credentials():
    """P0-4：runtime_account（进组件/指纹链路）不得带明文凭据。"""
    from modules.apps.collection_center.executor_v2 import _build_runtime_account

    runtime_account = _build_runtime_account(
        "shopee",
        {
            "account_id": "shopee_sg_x",
            "proxy_enabled": True,
            "proxy_server": "http://u:p@h:8080",
            "proxy_username": "u",
            "proxy_password": "p",
        },
    )
    assert "proxy_username" not in runtime_account
    assert "proxy_password" not in runtime_account
    assert runtime_account["proxy_server"] == "http://h:8080"


def test_runtime_task_params_drop_proxy_credentials():
    """P0-4：组件 config（params["account"]）不得带明文凭据。"""
    from pathlib import Path

    from modules.apps.collection_center.executor_v2 import _build_runtime_task_params

    params = _build_runtime_task_params(
        task_id="task-1",
        account={
            "account_id": "shopee_sg_x",
            "proxy_server": "http://u:p@h:8080",
            "proxy_username": "u",
            "proxy_password": "p",
        },
        platform="shopee",
        granularity="daily",
        normalized_date_range={"date_from": "2025-01-01", "date_to": "2025-01-31"},
        task_download_dir=Path("tmp"),
        screenshot_dir=Path("tmp"),
        reused_session=False,
    )
    assert "proxy_username" not in params["account"]
    assert "proxy_password" not in params["account"]
    assert params["account"]["proxy_server"] == "http://h:8080"


async def test_account_proxy_reaches_browser_context_in_storage_state_path(monkeypatch):
    """P1-3：账号代理必须真正落到 browser.new_context(proxy=...)。

    这条走真实链路（指纹层注入 → context options 白名单 → new_context），
    回退 device_fingerprint 的 `if proxy:` 或任一处白名单都会红。
    """
    from modules.apps.collection_center import runtime_session

    captured: dict[str, object] = {}

    class _FakeContext:
        async def new_page(self):
            return object()

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            captured.update(kwargs)
            return _FakeContext()

    monkeypatch.setattr(
        "modules.utils.sessions.device_fingerprint.DeviceFingerprintManager."
        "get_or_create_fingerprint",
        lambda self, platform, account_id, account_config=None: dict(
            _FAKE_FINGERPRINT
        ),
    )

    await runtime_session.open_storage_state_runtime_bundle(
        browser=_FakeBrowser(),
        platform="shopee",
        session_owner_id="main-1",
        account={"account_id": "shopee_sg_x"},
        storage_state={"cookies": [], "origins": []},
        proxy={
            "server": "http://10.0.0.9:8080",
            "username": "u",
            "password": "p",
        },
    )

    assert captured["proxy"] == {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }


async def test_runtime_fingerprint_failure_fallback_keeps_account_proxy(monkeypatch):
    """O1：指纹加载失败回退时，context options 仍必须带账号代理。

    ``get_browser_context_args()`` 明确不含 proxy —— 回退时漏掉就是
    **静默直连**（账号从宿主 IP 出现，IP 隔离形同虚设）。
    """
    from modules.apps.collection_center import runtime_session

    async def _broken_fingerprint(*args, **kwargs):
        raise RuntimeError("fingerprint broken")

    monkeypatch.setattr(
        runtime_session,
        "_get_fingerprint_context_options_async",
        _broken_fingerprint,
    )

    proxy = {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }
    context_options = await runtime_session.build_runtime_context_options(
        platform="shopee",
        session_owner_id="main-1",
        account={"account_id": "shopee_sg_x"},
        proxy=proxy,
    )

    assert context_options["proxy"] == proxy


async def test_runtime_context_options_fingerprint_failure_fallback_keeps_account_proxy(
    monkeypatch,
):
    """O1：指纹链路失败后的回退分支同样必须带账号代理。

    Task 4.2 删掉了 executor 侧那份死代码（``_prepare_runtime_page_bundle``），
    活着的回退分支在 ``runtime_session.build_runtime_context_options``：
    指纹取不到时回退到全局 context 参数，但**必须显式带上账号代理** ——
    漏掉就是「静默直连」（账号从宿主 IP 出现，IP 隔离形同虚设）。
    """
    from modules.apps.collection_center import runtime_session

    async def _broken_fingerprint(*args, **kwargs):
        raise RuntimeError("fingerprint broken")

    monkeypatch.setattr(
        runtime_session,
        "_get_fingerprint_context_options_async",
        _broken_fingerprint,
    )

    proxy = {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }
    context_options = await runtime_session.build_runtime_context_options(
        platform="shopee",
        session_owner_id="main-1",
        account={"account_id": "shopee_sg_x"},
        proxy=proxy,
    )

    assert context_options["proxy"] == proxy


async def test_account_proxy_reaches_browser_context_in_parallel_fanout(monkeypatch, tmp_path):
    """P1-3：并行扇出的每个 context 都必须带账号代理。

    这条同时钉住 executor 侧的兜底解析（``proxy = proxy or resolve_account_proxy(account)``）：
    账号 dict 里的凭据被剔除只是发生在组件 config 上，executor 拿到的原始
    account 仍然带凭据，兜底解析必须拿得到完整代理。
    """
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    # P0：必须给 executor 注入**独立**的 coordinator 实例。
    # 默认拿到的是模块级单例（backend/services/main_account_session_coordinator.py:60），
    # 直接改它的方法会永久污染全局：后续用例里的第二个任务不再等锁，
    # 抢在第一个任务写入新会话前就加载了旧会话，断言假红
    # （test_collection_executor_reused_session_scope::test_execute_reloads_main_account_session_after_waiting_for_lock）。
    executor = CollectionExecutorV2(
        main_account_session_coordinator=MainAccountSessionCoordinator()
    )
    executor.downloads_dir = tmp_path / "downloads"
    executor.screenshots_dir = tmp_path / "screenshots"
    executor._update_status = AsyncMock()
    executor._process_files = AsyncMock(return_value=[])
    executor._start_browser_diagnostics = AsyncMock(return_value=None)
    executor._ensure_login_gate_ready = AsyncMock()

    class _DummyLock:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return None

    # 只改这个用例自己持有的 coordinator 实例，不碰模块级单例。
    coordinator = executor.main_account_session_coordinator
    coordinator.acquire = lambda platform, main_account_id: _DummyLock()
    coordinator.is_locked = lambda platform, main_account_id: False
    coordinator.waiter_count = lambda platform, main_account_id: 0

    captured_context_kwargs: list[dict] = []

    class _FakePage:
        url = "https://seller.shopee.cn/"

    class _FakeContext:
        async def add_init_script(self, script: str) -> None:
            return None

        async def new_page(self):
            return _FakePage()

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            captured_context_kwargs.append(kwargs)
            return _FakeContext()

    async def _fake_open_runtime_bundle(**kwargs):
        return type(
            "Bundle",
            (),
            {
                "reused_session": False,
                "context": type(
                    "Ctx",
                    (),
                    {"close": AsyncMock(), "cookies": AsyncMock(return_value=[])},
                )(),
                "page": type("Page", (), {"close": AsyncMock()})(),
                "mode": "storage_state_fanout",
            },
        )()

    monkeypatch.setattr(
        "modules.utils.sessions.device_fingerprint.DeviceFingerprintManager."
        "get_or_create_fingerprint",
        lambda self, platform, account_id, account_config=None: dict(
            _FAKE_FINGERPRINT
        ),
    )
    monkeypatch.setattr(executor, "_open_runtime_bundle", _fake_open_runtime_bundle)
    manifest_component = AsyncMock(
        return_value=type("R", (), {"success": True, "file_path": None, "message": ""})()
    )
    monkeypatch.setattr(
        executor,
        "_run_runtime_manifest_component",
        manifest_component,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session."
        "snapshot_runtime_storage_state",
        AsyncMock(return_value={"cookies": [], "origins": []}),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2."
        "_record_platform_shop_discovery_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.executor_v2.runtime_session."
        "apply_stealth_init_scripts",
        AsyncMock(),
    )

    await executor.execute_parallel_domains(
        task_id="task-proxy",
        platform="shopee",
        account_id="shopee_sg_x",
        account={
            "account_id": "shopee_sg_x",
            "main_account_id": "main-1",
            "login_url": "https://seller.shopee.cn",
            "proxy_enabled": True,
            "proxy_server": "http://10.0.0.9:8080",
            "proxy_username": "u",
            "proxy_password": "p",
        },
        data_domains=["orders"],
        date_range={"start": "2025-01-01", "end": "2025-01-31"},
        granularity="daily",
        browser=_FakeBrowser(),
        browser_type=object(),
        max_parallel=1,
        debug_mode=False,
        runtime_manifests={"login": {}, "exports_by_domain": {"orders": {}}},
    )

    assert captured_context_kwargs, "并行扇出必须创建 context"
    for kwargs in captured_context_kwargs:
        assert kwargs["proxy"] == {
            "server": "http://10.0.0.9:8080",
            "username": "u",
            "password": "p",
        }

    # P0-4：代理凭据只随 proxy= 下传，组件拿到的账号 dict / config 里不得有明文密码
    assert manifest_component.await_args_list
    for call in manifest_component.await_args_list:
        component_account = call.kwargs.get("account") or {}
        assert "proxy_username" not in component_account
        assert "proxy_password" not in component_account
        config_account = (call.kwargs.get("config") or {}).get("account") or {}
        assert "proxy_username" not in config_account
        assert "proxy_password" not in config_account


async def test_parallel_fanout_case_does_not_pollute_module_coordinator_singleton(
    monkeypatch,
    tmp_path,
):
    """P0 防复发：测试**不得**污染模块级 coordinator 单例。

    单例一旦被污染（``acquire`` 换成永不阻塞的假锁），后续用例里的第二个任务
    就不再等锁 —— 抢在第一个任务写入新会话前就加载了旧会话，断言假红
    （``test_collection_executor_reused_session_scope::
    test_execute_reloads_main_account_session_after_waiting_for_lock``）。

    这里取"执行前/执行后"的方法引用做对比，钉死全局单例不被用例改写。
    """
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
        get_main_account_session_coordinator,
    )

    singleton = get_main_account_session_coordinator()
    before = (singleton.acquire, singleton.is_locked, singleton.waiter_count)

    await test_account_proxy_reaches_browser_context_in_parallel_fanout(
        monkeypatch, tmp_path
    )

    after = (singleton.acquire, singleton.is_locked, singleton.waiter_count)
    assert after == before, "模块级 coordinator 单例被用例污染了"
    # 单例必须仍是类上的原始实现（没有被实例属性覆盖）
    assert before[0] == MainAccountSessionCoordinator.acquire.__get__(singleton)
    assert before[1] == MainAccountSessionCoordinator.is_locked.__get__(singleton)
    assert before[2] == MainAccountSessionCoordinator.waiter_count.__get__(singleton)


async def test_headful_login_fallback_uses_passed_proxy_with_credentials(monkeypatch):
    """有头登录回退必须用**调用方已解析好的**代理（含凭据）。

    account 进入回退前已被 strip（凭据已删），若在回退里从 account 重新解析，
    需要认证的代理会收到 407 —— 人工登录流程在最需要它的场景走不通。

    Task 4.5 起，回退在**同一个 profile 目录**上开持久 context，代理必须原样
    透传到 ``launch_persistent_context``（浏览器进程级参数）。
    """
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._ensure_login_gate_ready = AsyncMock()
    executor._run_runtime_manifest_component = AsyncMock(
        return_value=SimpleNamespace(success=True)
    )

    launched: list[dict] = []

    class _FakeContext:
        pages: list = []

        async def new_page(self):
            return object()

        async def close(self):
            return None

    class _FakeChromium:
        async def launch_persistent_context(self, **kwargs):
            launched.append(kwargs)
            return _FakeContext()

    async def _fake_build_runtime_context_options(**kwargs):
        return {"viewport": {"width": 1280, "height": 800}, "accept_downloads": True}

    monkeypatch.setattr(
        "modules.apps.collection_center.runtime_session.build_runtime_context_options",
        _fake_build_runtime_context_options,
    )

    proxy = {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }

    await executor._run_headful_login_fallback(
        task_id="task-1",
        platform="shopee",
        # account 已被 strip：没有凭据
        account={"account_id": "shopee_sg_x", "proxy_server": "http://10.0.0.9:8080"},
        params={"params": {}, "account": {"account_id": "shopee_sg_x"}},
        browser=None,
        old_context=object(),
        session_platform="",
        session_account_id="",
        runtime_manifests={"login": {"component": "login"}},
        proxy=proxy,
        browser_type=_FakeChromium(),
        profile_path="/tmp/profiles/shopee/shopee_sg_x",
        launch_kwargs={"headless": True},
    )

    assert launched, "有头回退必须走 launch_persistent_context"
    # 有头阶段与重开阶段都必须是**同一个带凭据的代理对象**
    for call in launched:
        assert call["proxy"] == {
            "server": "http://10.0.0.9:8080",
            "username": "u",
            "password": "p",
        }


async def test_headful_login_fallback_receives_resolved_proxy_from_caller(monkeypatch):
    """回退必须收到调用方传下来的 proxy（带凭据），不能从已 strip 的 account 重解析。"""
    from datetime import datetime

    from modules.apps.collection_center.executor_v2 import (
        CollectionExecutorV2,
        TaskContext,
        VerificationRequiredError,
    )

    executor = CollectionExecutorV2()
    executor._update_status = AsyncMock()
    executor._check_cancelled = AsyncMock()
    executor.popup_handler.close_popups = AsyncMock()
    executor._ensure_login_gate_ready = AsyncMock()

    fallback = AsyncMock(return_value=(True, object(), object()))
    monkeypatch.setattr(executor, "_run_headful_login_fallback", fallback)
    monkeypatch.setattr(
        executor,
        "_execute_python_component",
        AsyncMock(
            side_effect=VerificationRequiredError("manual_intervention", "shot.png")
        ),
    )

    proxy = {
        "server": "http://10.0.0.9:8080",
        "username": "u",
        "password": "p",
    }
    await executor._execute_with_python_components(
        task_id="task-1",
        platform="shopee",
        account={"account_id": "shopee_sg_x"},
        params={"params": {}, "account": {"account_id": "shopee_sg_x"}},
        context=TaskContext(
            task_id="task-1",
            platform="shopee",
            account_id="shopee_sg_x",
            data_domains=[],
            date_range={"start": "2026-03-01", "end": "2026-03-01"},
            granularity="daily",
        ),
        browser=object(),
        play_context=object(),
        page=object(),
        step_popup_handler=object(),
        task_download_dir=object(),
        data_domains=[],
        sub_domains=None,
        total_domains_count=0,
        start_time=datetime.now(),
        session_platform="",
        session_account_id="",
        runtime_manifests=None,
        proxy=proxy,
    )

    fallback.assert_awaited_once()
    assert fallback.await_args.kwargs["proxy"] == proxy

