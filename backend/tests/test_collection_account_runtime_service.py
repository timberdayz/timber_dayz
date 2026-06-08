import pytest


def test_classify_disabled_shop_account():
    from backend.services.collection_account_runtime_service import (
        CollectionAccountRuntimeError,
        classify_account_runtime_error,
    )

    error = classify_account_runtime_error(
        shop_exists=True,
        shop_enabled=False,
        main_exists=True,
        main_enabled=True,
    )

    assert isinstance(error, CollectionAccountRuntimeError)
    assert error.code == "shop_account_disabled"
    assert "已禁用" in error.user_message


def test_classify_missing_main_account():
    from backend.services.collection_account_runtime_service import (
        CollectionAccountRuntimeError,
        classify_account_runtime_error,
    )

    error = classify_account_runtime_error(
        shop_exists=True,
        shop_enabled=True,
        main_exists=False,
        main_enabled=None,
    )

    assert isinstance(error, CollectionAccountRuntimeError)
    assert error.code == "main_account_missing"
    assert "主账号不存在" in error.user_message


def test_map_missing_encryption_key_error():
    from backend.services.collection_account_runtime_service import (
        CollectionAccountRuntimeError,
        map_account_loader_exception,
    )

    error = map_account_loader_exception(
        RuntimeError("collector missing ACCOUNT_ENCRYPTION_KEY for account password decryption")
    )

    assert isinstance(error, CollectionAccountRuntimeError)
    assert error.code == "encryption_key_missing"
    assert "加密密钥" in error.user_message


def test_map_decrypt_failure_error():
    from backend.services.collection_account_runtime_service import (
        CollectionAccountRuntimeError,
        map_account_loader_exception,
    )

    error = map_account_loader_exception(ValueError("密码解密失败: 无效的密钥或数据已损坏"))

    assert isinstance(error, CollectionAccountRuntimeError)
    assert error.code == "password_decryption_failed"
    assert "密码解密失败" in error.user_message


@pytest.mark.asyncio
async def test_load_collection_account_runtime_raises_missing_key_before_not_found_message(
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.services.collection_account_runtime_service import (
        CollectionAccountRuntimeError,
        load_collection_account_runtime,
    )

    class _FakeShop:
        id = 1
        shop_account_id = "miaoshou_real_001"
        main_account_id = "miaoshou_real_001"
        platform = "miaoshou"
        enabled = True

    class _FakeMain:
        id = 2
        main_account_id = "miaoshou_real_001"
        platform = "miaoshou"
        enabled = True

    class _FakeShopLoader:
        async def load_shop_account_async(self, account_id, db):  # noqa: ANN001
            raise RuntimeError("collector missing ACCOUNT_ENCRYPTION_KEY for account password decryption")

    class _FakeAccountLoader:
        async def load_account_async(self, account_id, db):  # noqa: ANN001
            raise RuntimeError("collector missing ACCOUNT_ENCRYPTION_KEY for account password decryption")

    async def _fake_probe(account_id, db):  # noqa: ANN001
        return _FakeShop(), _FakeMain()

    monkeypatch.setattr(
        "backend.services.collection_account_runtime_service.get_shop_account_loader_service",
        lambda: _FakeShopLoader(),
    )
    monkeypatch.setattr(
        "backend.services.collection_account_runtime_service.get_account_loader_service",
        lambda: _FakeAccountLoader(),
    )
    monkeypatch.setattr(
        "backend.services.collection_account_runtime_service.probe_account_runtime_state",
        _fake_probe,
    )

    with pytest.raises(CollectionAccountRuntimeError) as exc_info:
        await load_collection_account_runtime("miaoshou_real_001", db=object())

    assert exc_info.value.code == "encryption_key_missing"
    assert "not found or disabled" not in exc_info.value.user_message
