import types

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
