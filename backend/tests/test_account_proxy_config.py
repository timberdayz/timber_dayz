"""P1 账号级代理配置透出契约。

代理配置存在 ``core.shop_accounts.extra_config["proxy"]`` 里（本计划不加列、
不写迁移），由 ``AccountLoaderService`` 透出成平铺键，供后续任务把它接到
浏览器代理链路。

这里只锁"账号 dict 里能读到这三个键"这一层契约，不涉及浏览器注入。
"""

from types import SimpleNamespace

from backend.services.account_loader_service import AccountLoaderService


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
