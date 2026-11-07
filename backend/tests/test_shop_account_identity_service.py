"""``backend/services/shop_account_identity_service.py`` 的契约测试。

三组断言:

1. 取值语义 —— 主数据登记值原样返回;主数据为空 ⇒ 留空(不猜、不回退);
2. 主数据读取 —— 真的从 ``core.shop_accounts`` 读到登记值(``pg_session`` 真实 PG);
3. 防回归 —— 仓库里不再存在硬编码覆盖表, 也不再有人 import 已删的旧 resolver。
"""

from pathlib import Path
from types import SimpleNamespace
import re

import pytest

from backend.services.shop_account_identity_service import (
    MasterShopIdentity,
    identity_from_shop_account_row,
    is_operating_store,
    load_master_identities,
    normalize_master_platform_shop_id,
    pick_master_platform_shop_id,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _identity(**overrides) -> MasterShopIdentity:
    base = {
        "shop_account_id": "shopee_sg_demo_local",
        "platform": "shopee",
        "platform_shop_id": "1407964586",
        "store_name": "demo.sg",
        "shop_region": "SG",
        "enabled": True,
        "business_role": "operating_store",
    }
    base.update(overrides)
    return MasterShopIdentity(**base)


# ---------------------------------------------------------------------------
# 1. 取值语义
# ---------------------------------------------------------------------------


def test_pick_master_platform_shop_id_returns_empty_for_missing_identity():
    assert pick_master_platform_shop_id(None) == ""


def test_pick_master_platform_shop_id_returns_empty_when_master_has_no_value():
    assert pick_master_platform_shop_id(_identity(platform_shop_id="")) == ""
    assert pick_master_platform_shop_id(_identity(platform_shop_id="   ")) == ""


def test_pick_master_platform_shop_id_returns_registered_value():
    assert pick_master_platform_shop_id(_identity()) == "1407964586"


def test_normalize_master_platform_shop_id_trims_and_maps_empty_to_empty():
    assert normalize_master_platform_shop_id("  1407964586  ") == "1407964586"
    assert normalize_master_platform_shop_id(None) == ""
    assert normalize_master_platform_shop_id("") == ""


def test_is_operating_store_requires_enabled_and_operating_store_role():
    assert is_operating_store(_identity()) is True
    assert is_operating_store(_identity(enabled=False)) is False
    assert is_operating_store(_identity(business_role="collection_source")) is False
    assert is_operating_store(None) is False


def test_identity_from_shop_account_row_reads_master_row():
    row = SimpleNamespace(
        shop_account_id="shopee_sg_demo_local",
        platform="Shopee",
        platform_shop_id="1407964586",
        store_name="demo.sg",
        shop_region="SG",
        enabled=True,
        business_role="operating_store",
    )

    identity = identity_from_shop_account_row(row)

    assert identity is not None
    assert identity.platform == "shopee"
    assert identity.platform_shop_id == "1407964586"
    assert identity.business_role == "operating_store"
    assert is_operating_store(identity) is True


def test_identity_from_shop_account_row_returns_none_for_non_master_object():
    assert identity_from_shop_account_row(SimpleNamespace(account_id="acc-1")) is None
    assert identity_from_shop_account_row(None) is None


# ---------------------------------------------------------------------------
# 2. 主数据读取(真实 PostgreSQL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_master_identities_returns_registered_value_only(pg_session):
    from modules.core.db import MainAccount, ShopAccount

    main_account = MainAccount(
        platform="shopee",
        main_account_id="identity-test-main",
        main_account_name="identity-test-main",
        username="main-user",
        password_encrypted="encrypted",
        login_url="https://seller.shopee.cn",
        enabled=True,
    )
    pg_session.add(main_account)
    await pg_session.flush()

    shop_account = ShopAccount(
        platform="shopee",
        shop_account_id="identity-test-shop",
        main_account_id="identity-test-main",
        store_name="identity-test.sg",
        platform_shop_id="1407964586",
        platform_shop_id_status="confirmed",
        shop_region="SG",
        business_role="operating_store",
        enabled=True,
    )
    pg_session.add(shop_account)
    await pg_session.flush()

    identities = await load_master_identities(
        pg_session, ["identity-test-shop", "identity-test-missing"]
    )

    assert identities["identity-test-shop"].platform_shop_id == "1407964586"
    assert (
        pick_master_platform_shop_id(identities["identity-test-shop"]) == "1407964586"
    )
    assert "identity-test-missing" not in identities
    assert pick_master_platform_shop_id(identities.get("identity-test-missing")) == ""


@pytest.mark.asyncio
async def test_load_master_identities_returns_empty_for_blank_input(pg_session):
    assert await load_master_identities(pg_session, []) == {}
    assert await load_master_identities(pg_session, ["", "   "]) == {}


# ---------------------------------------------------------------------------
# 3. 防回归:硬编码覆盖表与旧 resolver 不得复活
# ---------------------------------------------------------------------------


def _iter_runtime_sources():
    for folder in ("backend/services", "modules"):
        base = _REPO_ROOT / folder
        for path in base.rglob("*.py"):
            yield path


def test_no_hardcoded_shopee_shop_id_override_tables_exist():
    forbidden = (
        "SHOPEE_PLATFORM_SHOP_ID_OVERRIDES",
        "SHOPEE_STORE_NAME_OVERRIDES",
    )
    hits = []
    for path in _iter_runtime_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in forbidden:
            if name in text:
                hits.append(f"{path.relative_to(_REPO_ROOT)}: {name}")
    assert hits == [], f"硬编码覆盖表不得复活: {hits}"


def test_legacy_resolver_module_is_gone_and_not_imported():
    legacy = _REPO_ROOT / "backend/services/shopee_shop_id_resolver.py"
    assert not legacy.exists(), "旧 resolver 必须删除"

    # 只判「import 语句」—— 文档里提到旧文件名是允许的(历史说明)。
    import_pattern = re.compile(
        r"^\s*(?:from\s+[\w.]*shopee_shop_id_resolver\s+import|import\s+[\w.]*shopee_shop_id_resolver)",
        re.MULTILINE,
    )
    hits = []
    for path in _iter_runtime_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if import_pattern.search(text):
            hits.append(str(path.relative_to(_REPO_ROOT)))
    assert hits == [], f"不得再 import 已删的旧 resolver: {hits}"
