"""账号级代理配置解析契约。

代理配置存在 ``core.shop_accounts.extra_config["proxy"]``（不加列、不写迁移），
解析规则集中在 ``backend/services/account_proxy_config.py``：
AccountLoaderService 与 ShopAccountLoaderService 共用同一套规则，
测试直接打在这套共享纯函数上。

规范：docs/guides/COLLECTION_SESSION_LIFECYCLE.md P1~P4
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


def _make_service() -> AccountLoaderService:
    """构造一个不需要真实密钥的 loader（测试里不需要真的解密）。"""
    service = AccountLoaderService()
    service._decrypt_password = lambda encrypted: "plain-password"
    return service


def _make_main_account() -> SimpleNamespace:
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


def test_resolve_account_proxy_never_uses_legacy_region_pool(monkeypatch):
    """C1：自有代理场景绝不调用遗留 proxy_config_manager（否则一账号两个 IP）。"""
    import modules.utils.proxy_config_manager as legacy_module

    def _fail(*args, **kwargs):
        raise AssertionError("自有代理场景不得走遗留地区池链路")

    monkeypatch.setattr(
        legacy_module.proxy_config_manager, "get_playwright_proxy_config", _fail
    )
    monkeypatch.setattr(legacy_module, "get_account_proxy", _fail)

    resolved = resolve_account_proxy(
        {
            "proxy_enabled": True,
            "proxy_server": "http://10.0.0.9:8080",
            "proxy_region": "sg",
        }
    )
    assert resolved == {"server": "http://10.0.0.9:8080"}


def test_account_proxy_chain_never_references_legacy_direct_fallback():
    """C2：新链路不得引用遗留链路（fallback_to_direct 会静默直连 → 账号从宿主 IP 出现）。"""
    import ast
    import inspect

    from backend.services import account_proxy_config

    tree = ast.parse(inspect.getsource(account_proxy_config))
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                referenced.add(alias.name)

    assert "proxy_config_manager" not in referenced
    assert "get_playwright_proxy_config" not in referenced
    assert "fallback_to_direct" not in referenced


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
