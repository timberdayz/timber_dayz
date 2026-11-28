"""费用接口的店铺范围契约。"""

import pytest
from sqlalchemy import String, column

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

    def fetchall(self):
        return self._rows


class _DB:
    def __init__(self, rows, tenants=None):
        self.rows = rows
        self.tenants = tenants or []
        self.executed = []

    async def execute(self, query, params=None):
        sql = str(query)
        self.executed.append((sql, params))
        if "main_account_name" in sql:
            return _ScalarRows(self.tenants)
        return _ScalarRows(self.rows)


class _MainAccount:
    """租户维度的最小桩：让 ``_load_main_account_names`` 真的查出租户名。

    ⚠️ 必须用 ``column()`` 显式声明：SQLAlchemy 2.0 对裸字符串属性做 select 会直接
    抛 "Textual column expression ... should be explicitly declared with text()"，
    租户名会静默退化成空串，断言就变成假绿。
    """

    main_account_id = column("main_account_id", String)
    main_account_name = column("main_account_name", String)


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
    monkeypatch.setattr(module, "MainAccount", _MainAccount)

    # ⚠️ 必须显式传 include_disabled=False：路由签名里的默认值是 FastAPI 的 Query 对象，
    # 直接当普通函数调用时它是真值，``not include_disabled`` 恒为 False，过滤条件不会进 SQL。
    result = await module.list_expense_shops(
        include_disabled=False, db=db, current_user=_make_user()
    )

    # SQLAlchemy 把枚举值渲染成绑定参数，SQL 文本里是 business_role 而非 operating_store
    shop_sql = [sql for sql, _ in db.executed if "business_role" in sql]
    assert shop_sql, "必须查询运营店铺（business_role = operating_store）"
    # ⚠️ 不能只断言 "enabled" in sql —— SELECT 列表里本来就有 enabled，恒真。
    # 必须断言**过滤条件**本身存在。
    assert (
        "core.shop_accounts.enabled IS true" in shop_sql[0]
    ), "默认路径必须带 enabled IS true 过滤；include_disabled=true 才放行停用店"
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

    db = _DB([disabled], tenants=[("main-1", "租户一")])
    monkeypatch.setattr(module, "get_async_db", lambda: db)
    monkeypatch.setattr(module, "MainAccount", _MainAccount)

    result = await module.list_expense_shops(
        include_disabled=True, db=db, current_user=_make_user()
    )

    items = result["data"]
    assert len(items) == 1
    item = items[0]
    assert item["enabled"] is False
    assert item["internal_code"] == "ETERNALBLOOM_SG"
    assert item["main_account_id"] == "main-1"
    assert item["main_account_name"] == "租户一", "租户名必须真的从主账号表查出来"
    assert item["platform_shop_id"] == "1292370001"
    assert item["shop_account_id"] == "shopee_sg_eternalbloom_local"


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
