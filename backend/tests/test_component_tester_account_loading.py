import types
from pathlib import Path

from backend.services.component_test_service import ComponentTestService
from tools.test_component import ComponentTester


def test_component_tester_get_account_info_supports_get_all_local_accounts(monkeypatch):
    tester = ComponentTester(platform="miaoshou", account_id="miaoshou_real_001")

    fake_module = types.SimpleNamespace(
        get_all_local_accounts=lambda: [
            {
                "account_id": "miaoshou_real_001",
                "platform": "miaoshou",
                "username": "demo",
            }
        ]
    )

    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
    monkeypatch.setattr("importlib.util.spec_from_file_location", lambda *args, **kwargs: types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda module: module.__dict__.update(fake_module.__dict__))))
    monkeypatch.setattr("importlib.util.module_from_spec", lambda spec: types.SimpleNamespace())

    account = tester.get_account_info()

    assert account["account_id"] == "miaoshou_real_001"
    assert account["platform"] == "miaoshou"


def test_prepare_account_info_preserves_phone_email_and_shop_region(monkeypatch):
    class _FakeAccount:
        account_id = "Tiktok 2店"
        platform = "Tiktok"
        username = "chenzeweinbnb@163.com"
        password_encrypted = "encrypted"
        store_name = "Tiktok 2店"
        login_url = "https://seller.tiktokglobalshop.com"
        cookies_file = None
        capabilities = {"analytics": True}
        email = "chenzeweinbnb@163.com"
        phone = "18876067809"
        region = "CN"
        currency = "SGD"
        shop_region = "SG"
        notes = "demo"

    class _FakeEncryptionService:
        def decrypt_password(self, encrypted):  # noqa: ANN001
            assert encrypted == "encrypted"
            return "plain-password"

    monkeypatch.setattr(
        "backend.services.component_test_service.get_encryption_service",
        lambda: _FakeEncryptionService(),
    )

    account_info = ComponentTestService.prepare_account_info(_FakeAccount())

    assert account_info["username"] == "chenzeweinbnb@163.com"
    assert account_info["password"] == "plain-password"
    assert account_info["email"] == "chenzeweinbnb@163.com"
    assert account_info["phone"] == "18876067809"
    assert account_info["shop_region"] == "SG"


def test_prepare_account_info_uses_platform_login_entry_for_shopee(monkeypatch):
    class _FakeAccount:
        account_id = "shopee_ph_demo_local"
        platform = "shopee"
        username = "hongxikeji:main"
        password_encrypted = "encrypted"
        store_name = "demo.ph"
        login_url = "https://seller.shopee.cn"
        cookies_file = None
        capabilities = {"products": True}
        email = ""
        phone = ""
        region = "CN"
        currency = "CNY"
        shop_region = "PH"
        notes = "demo"

    class _FakeEncryptionService:
        def decrypt_password(self, encrypted):  # noqa: ANN001
            assert encrypted == "encrypted"
            return "plain-password"

    monkeypatch.setattr(
        "backend.services.component_test_service.get_encryption_service",
        lambda: _FakeEncryptionService(),
    )

    account_info = ComponentTestService.prepare_account_info(_FakeAccount())

    assert (
        account_info["login_url"]
        == "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
    )


def test_prepare_account_info_fills_missing_shopee_shop_id_from_override(monkeypatch):
    class _FakeAccount:
        account_id = "shopee_my_xhkj1_local"
        platform = "shopee"
        username = "hongxikeji:main"
        password_encrypted = "encrypted"
        store_name = "xhkj1.my"
        login_url = "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
        cookies_file = None
        capabilities = {"products": True}
        email = ""
        phone = ""
        region = "CN"
        currency = "CNY"
        shop_region = "MY"
        notes = "demo"
        platform_shop_id = ""

    class _FakeEncryptionService:
        def decrypt_password(self, encrypted):  # noqa: ANN001
            assert encrypted == "encrypted"
            return "plain-password"

    monkeypatch.setattr(
        "backend.services.component_test_service.get_encryption_service",
        lambda: _FakeEncryptionService(),
    )

    account_info = ComponentTestService.prepare_account_info(_FakeAccount())

    assert account_info["shop_id"] == "1540271739"
    assert account_info["platform_shop_id"] == "1540271739"


def test_prepare_account_info_ignores_invalid_nonnumeric_shopee_shop_id_and_uses_override(monkeypatch):
    class _FakeAccount:
        account_id = "shopee_sg_hx_home_local"
        platform = "shopee"
        username = "leslieshop:main"
        password_encrypted = "encrypted"
        store_name = "hx_home.sg"
        login_url = "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
        cookies_file = None
        capabilities = {"products": True}
        email = ""
        phone = ""
        region = "CN"
        currency = "CNY"
        shop_region = "SG"
        notes = "demo"
        platform_shop_id = "xihong"

    class _FakeEncryptionService:
        def decrypt_password(self, encrypted):  # noqa: ANN001
            assert encrypted == "encrypted"
            return "plain-password"

    monkeypatch.setattr(
        "backend.services.component_test_service.get_encryption_service",
        lambda: _FakeEncryptionService(),
    )

    account_info = ComponentTestService.prepare_account_info(_FakeAccount())

    assert account_info["shop_id"] == "1391124228"
    assert account_info["platform_shop_id"] == "1391124228"


def test_component_versions_router_uses_shop_account_loader_without_platform_account_fallback():
    text = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/collection/routers/component_versions.py"
    ).read_text(encoding="utf-8")

    assert "get_shop_account_loader_service" in text
    assert "select(PlatformAccount)" not in text


def test_account_loader_service_is_backed_by_main_and_shop_accounts():
    text = (
        Path(__file__).resolve().parents[2]
        / "backend/services/account_loader_service.py"
    ).read_text(encoding="utf-8")

    assert "MainAccount" in text
    assert "ShopAccount" in text
    assert "ShopAccountCapability" in text
    assert "PlatformAccount" not in text
