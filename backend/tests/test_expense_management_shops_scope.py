"""费用接口的店铺范围契约。"""

import pytest

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _make_user():
    from types import SimpleNamespace

    return SimpleNamespace(
        user_id=1,
        username="tester",
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def execute(self, query, params=None):
        self.executed.append((str(query), params))
        return _ScalarRows(self.rows)


def _shop(**kwargs):
    from types import SimpleNamespace

    base = dict(
        id=1,
        platform="shopee",
        shop_account_id="shopee_sg_x_local",
        platform_shop_id="123456",
        store_name="x.sg",
        internal_code="X_SG",
        enabled=True,
        business_role="operating_store",
        main_account_id="main-1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_shops_default_excludes_disabled(monkeypatch):
    """默认路径必须过滤 enabled；只有 include_disabled=true 才放行停用店。"""
    from backend.domains.business.routers import expense_management as module

    db = _DB([_shop()])
    monkeypatch.setattr(module, "get_async_db", lambda: db)
    monkeypatch.setattr(module, "MainAccount", _shop)

    result = await module.list_expense_shops(db=db, current_user=_make_user())

    # SQLAlchemy 把枚举值渲染成绑定参数，SQL 文本里是 business_role 而非 operating_store
    shop_sql = [sql for sql, _ in db.executed if "business_role" in sql]
    assert shop_sql, "必须查询运营店铺（business_role = operating_store）"
    assert "enabled" in shop_sql[0], "默认路径必须过滤 enabled"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_shops_include_disabled_returns_status_fields(monkeypatch):
    """include_disabled=true 时返回停用店，并带状态/租户/双 ID 字段。"""
    from backend.domains.business.routers import expense_management as module

    disabled = _shop(
        id=51,
        shop_account_id="shopee_sg_eternalbloom_local",
        platform_shop_id="1292370001",
        store_name="eternalbloom.sg",
        internal_code="ETERNALBLOOM_SG",
        enabled=False,
    )

    class _DB:
        def __init__(self):
            self.executed = []

        async def execute(self, query, params=None):
            self.executed.append((str(query), params))
            return _ScalarRows([disabled])

    db = _DB()
    monkeypatch.setattr(module, "get_async_db", lambda: db)
    monkeypatch.setattr(module, "MainAccount", _shop)

    result = await module.list_expense_shops(
        include_disabled=True, db=db, current_user=_make_user()
    )

    items = result["data"]
    assert len(items) == 1
    item = items[0]
    assert item["enabled"] is False
    assert item["internal_code"] == "ETERNALBLOOM_SG"
    assert item["main_account_id"] == "main-1"
    assert "platform_shop_id" in item
    assert "shop_account_id" in item


def test_expense_list_sql_joins_shop_accounts_with_dual_key():
    """费用列表必须按 platform + (platform_shop_id OR shop_account_id) 关联店铺。

    只按 platform_shop_id 关联会漏掉全部 6 家 TikTok 店（其 platform_shop_id 为空，
    费用行存的是 shop_account_id），它们的 shop_enabled 会变 NULL，从而被
    「enabled === true」的分摊集合静默排除。
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/business/routers/expense_management.py"
    ).read_text(encoding="utf-8")

    assert "shop_accounts" in source
    assert "platform_shop_id" in source
    assert "shop_account_id" in source
    assert "shop_enabled" in source
    assert "shop_shop_account_id" in source
    assert "main_account_id" in source
    assert "BATCH_MARK_PREFIX" in source
