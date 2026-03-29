import types

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
