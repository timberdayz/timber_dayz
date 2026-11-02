"""账号级代理配置解析契约。

代理配置存在 ``core.shop_accounts.extra_config["proxy"]``（不加列、不写迁移），
解析规则集中在 ``backend/services/account_proxy_config.py``：
AccountLoaderService 与 ShopAccountLoaderService 共用同一套规则，
测试直接打在这套共享纯函数上。

规范：docs/guides/COLLECTION_SESSION_LIFECYCLE.md P1~P4
"""

from types import SimpleNamespace

import pytest

from backend.services.account_loader_service import AccountLoaderService
from backend.services.account_proxy_config import (
    extract_proxy_config,
    mask_proxy_server,
    split_proxy_credentials,
)


def _make_service() -> AccountLoaderService:
    """构造一个不需要真实密钥的 loader（测试里不需要真的解密）。"""
    service = AccountLoaderService()
    service._decrypt_password = lambda encrypted: "plain-password"
    return service


def _make_main_account() -> SimpleNamespace:
    return SimpleNamespace(
        platform="shopee",
        main_account_id="shopee KR",
        username="demo-user",
        password_encrypted="enc",
        login_url="https://example.test/login",
    )


def _make_shop_account(extra_config) -> SimpleNamespace:
    return SimpleNamespace(
        platform="shopee",
        shop_account_id="shopee_sg_x",
        main_account_id="shopee KR",
        store_name="demo.sg",
        platform_shop_id="",
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
    # 无 scheme（运维漏写 http://）也要拆干净
    assert split_proxy_credentials("user:pass@h:8080") == {
        "server": "h:8080",
        "username": "user",
        "password": "pass",
    }


def test_mask_proxy_server_drops_credentials():
    """诊断字段用：凭据必须被抹掉（规范 §8 session_proxy 脱敏）。"""
    assert mask_proxy_server("http://user:pass@h:8080") == "http://h:8080"
    assert "pass" not in mask_proxy_server("http://user:pass@h:8080")
