import pytest

from modules.core.db import (
    MainAccount,
    PlatformShopDiscovery,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountCapability,
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (MainAccount, "main_accounts"),
        (ShopAccount, "shop_accounts"),
        (ShopAccountAlias, "shop_account_aliases"),
        (ShopAccountCapability, "shop_account_capabilities"),
        (PlatformShopDiscovery, "platform_shop_discoveries"),
    ],
)
def test_main_shop_account_tables_bind_explicitly_to_core_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "core"
    assert table.fullname == f"core.{table_name}"


def test_shop_account_alias_targets_shop_accounts():
    fk_targets = {fk.target_fullname for fk in ShopAccountAlias.__table__.foreign_keys}

    assert "core.shop_accounts.id" in fk_targets


def test_shop_account_capability_targets_shop_accounts():
    fk_targets = {fk.target_fullname for fk in ShopAccountCapability.__table__.foreign_keys}

    assert "core.shop_accounts.id" in fk_targets


def test_main_account_id_is_globally_unique():
    unique_columns = {column.name for column in MainAccount.__table__.columns if column.unique}

    assert "main_account_id" in unique_columns


def test_shop_account_id_is_globally_unique():
    unique_columns = {column.name for column in ShopAccount.__table__.columns if column.unique}

    assert "shop_account_id" in unique_columns
