"""代理**来源位**契约（纯源码，不碰数据库、不碰事件循环）。

守的是 R8.4「出口同源」里最容易被人改回去的那一条：

> 代理的**权威位在主账号** ``core.main_accounts.extra_config['proxy']``，
> 店铺级 ``core.shop_accounts.extra_config['proxy']`` 仅作**回退**。

为什么权威位必须在主账号
----------------------
业务上是「一个登录身份 = 一个设备 = 一个出口」。IP 隔离的目的就是让平台无法把
这些账号关联成「同一个出口的账号矩阵」⇒ 出口必须绑在**登录身份**上，
而不是绑在某一个店上（否则一个登录身份下两个店会出两个 IP，平台立刻判定环境异常）。

为什么单独一个文件（而不是并进 ``backend/tests/test_account_proxy_config.py``）
--------------------------------------------------------------------------
CI 的「Run root contract tests (no DB)」步骤只跑**清单里的文件**，
而清单里的每个文件都会被同一次 pytest 会话收集。

``backend/tests/test_account_proxy_config.py`` 里有 9 个 **async** 用例，
而 ``backend/tests/conftest.py`` 用 ``@pytest.fixture(scope="session")``
覆盖了 ``event_loop``。在 **CI 钉的** ``pytest==7.4.3`` /
``pytest-asyncio==0.21.1`` 下，这个覆盖**会生效**（pytest-asyncio 1.x 忽略它）⇒
把它放进根契约清单后，它排在
``backend/tests/test_celery_dispatch_event_loop_isolation.py`` 之后，
就会拿到**已被关闭**的 session 事件循环 ⇒ 9 个用例报
``RuntimeError: Event loop is closed``（2026-11-14 实测，CI run 43485663421）。

⇒ 本文件**只放纯同步断言**，才能安全进 CI 根契约清单。
异步用例留在 ``backend/tests/test_account_proxy_config.py``（由全量回归覆盖）。

规范：docs/guides/COLLECTION_SESSION_LIFECYCLE.md R8.4
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from backend.services.account_loader_service import AccountLoaderService


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_collect_and_inspection_read_the_same_proxy_source():
    """巡店与采集必须读**同一个来源** —— 否则登录 IP 与采集 IP 不一致。

    登录时 IP 与采集时 IP 不一致，平台立刻判定「环境突变」，比没有隔离更糟。
    """
    inspected = (REPO_ROOT / "scripts" / "pwcli_account_inventory.py").read_text(
        encoding="utf-8"
    )
    account_loader = (
        REPO_ROOT / "backend" / "services" / "account_loader_service.py"
    ).read_text(encoding="utf-8")
    shop_loader = (
        REPO_ROOT / "backend" / "services" / "shop_account_loader_service.py"
    ).read_text(encoding="utf-8")

    # 三处都必须先读主账号级，再回退店铺级
    for name, source in (
        ("pwcli_account_inventory", inspected),
        ("account_loader_service", account_loader),
        ("shop_account_loader_service", shop_loader),
    ):
        assert "main_account" in source, f"{name} 未读主账号级 extra_config"
        assert "extra_config" in source, f"{name} 未读 extra_config"

    assert "main_extra_config" in inspected, "巡店清单未取主账号级 extra_config"
    assert 'getattr(main_account, "extra_config"' in account_loader
    assert 'getattr(main_account, "extra_config"' in shop_loader
