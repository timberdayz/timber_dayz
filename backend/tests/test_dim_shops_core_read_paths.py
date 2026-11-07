import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    DimPlatform,
    DimShop,
    DimUser,
    Employee,
    EmployeeShopAssignment,
    PerformanceScore,
    SalesTarget,
    TargetBreakdown,
)


@pytest_asyncio.fixture
async def dim_shops_core_read_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in (
            "core",
            "a_class",
            "b_class",
            "c_class",
            "finance",
            "ops",
            "semantic",
        ):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        # 只建本用例需要的表：Base.metadata.create_all 会带上 PG 专有的
        # jsonb 默认值（'[]'::jsonb），sqlite 无法解析。
        for table in (
            DimPlatform.__table__,
            DimShop.__table__,
            DimUser.__table__,
            Employee.__table__,
            EmployeeShopAssignment.__table__,
            PerformanceScore.__table__,
            SalesTarget.__table__,
            TargetBreakdown.__table__,
        ):
            await conn.run_sync(table.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _request_stub():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


@pytest.mark.asyncio
async def test_target_breakdown_list_reads_shop_name_from_core_dim_shops(dim_shops_core_read_session):
    from backend.routers.target_management import list_breakdowns

    dim_shops_core_read_session.add(DimPlatform(platform_code="shopee", name="Shopee", is_active=True))
    dim_shops_core_read_session.add(
        DimShop(platform_code="shopee", shop_id="shop-1", shop_name="Core Shop", shop_slug="core-shop")
    )
    dim_shops_core_read_session.add(
        SalesTarget(
            id=1,
            target_name="Target 1",
            target_type="shop",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            target_amount=100.0,
            target_quantity=10,
            target_profit_amount=20.0,
            status="active",
        )
    )
    dim_shops_core_read_session.add(
        TargetBreakdown(
            target_id=1,
            breakdown_type="shop",
            platform_code="shopee",
            shop_id="shop-1",
            target_amount=100.0,
            target_quantity=10,
            target_profit_amount=20.0,
        )
    )
    await dim_shops_core_read_session.commit()

    response = await list_breakdowns(
        request=_request_stub(),
        target_id=1,
        breakdown_type="shop",
        db=dim_shops_core_read_session,
        current_user=SimpleNamespace(user_id=1),
    )
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["data"][0]["shop_name"] == "Core Shop"


@pytest.mark.asyncio
async def test_shop_performance_reads_shop_name_from_core_dim_shops(dim_shops_core_read_session):
    from backend.domains.business.routers.performance_management import get_shop_performance

    dim_shops_core_read_session.add(DimPlatform(platform_code="shopee", name="Shopee", is_active=True))
    dim_shops_core_read_session.add(
        DimShop(platform_code="shopee", shop_id="shop-2", shop_name="Perf Shop", shop_slug="perf-shop")
    )
    dim_shops_core_read_session.add(
        PerformanceScore(
            platform_code="shopee",
            shop_id="shop-2",
            period="2026-03",
            total_score=88.0,
            sales_score=20.0,
            profit_score=20.0,
            key_product_score=24.0,
            operation_score=24.0,
            performance_coefficient=1.1,
        )
    )
    await dim_shops_core_read_session.commit()

    response = await get_shop_performance(
        request=_request_stub(),
        shop_id="shop-2",
        platform_code="shopee",
        period="2026-03",
        db=dim_shops_core_read_session,
    )
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["data"]["shop_name"] == "Perf Shop"


@pytest.mark.asyncio
async def test_employee_assignment_list_resolves_shop_name_from_core_shop_accounts(
    dim_shops_core_read_session, monkeypatch
):
    """归属列表的店名来自权威主数据 core.shop_accounts，而不是派生表 core.dim_shops。

    佐证：commit 42c97563「core.dim_shops 是派生展示维度表…权威主数据是 core.shop_accounts」，
    旧用例的「读 dim_shops」前提已过期。店名解析用的是 PG 专有 SQL（``id::text``），
    sqlite 无法执行，因此这里：
    - 用源码契约钉死「读 core.shop_accounts、不读 core.dim_shops」；
    - 再用替身 loader 验证接口把权威店名透传到响应（派生表里的旧名不得被采用）。
    """
    from backend.domains.business.routers import hr_commission
    from backend.domains.business.routers.hr_commission import list_employee_shop_assignments

    source = Path("backend/domains/business/routers/hr_commission.py").read_text(
        encoding="utf-8"
    )
    loader_source = source[
        source.index("async def _load_shop_display_names") : source.index(
            "def _validate_shop_assignment_ratio_limit"
        )
    ]
    assert "FROM core.shop_accounts" in loader_source
    assert "FROM core.dim_shops" not in loader_source

    dim_shops_core_read_session.add(DimPlatform(platform_code="shopee", name="Shopee", is_active=True))
    dim_shops_core_read_session.add(
        DimShop(platform_code="shopee", shop_id="shop-3", shop_name="Derived Shop", shop_slug="commission-shop")
    )
    dim_shops_core_read_session.add(
        Employee(id=1, employee_code="E001", name="Alice")
    )
    dim_shops_core_read_session.add(
        EmployeeShopAssignment(
            id=1,
            year_month="2026-03",
            employee_code="E001",
            platform_code="shopee",
            shop_id="shop-3",
            status="active",
        )
    )
    await dim_shops_core_read_session.commit()

    async def _fake_loader(_db):
        return {("shopee", "shop-3"): "Authoritative Shop"}

    monkeypatch.setattr(hr_commission, "_load_shop_display_names", _fake_loader)

    response = await list_employee_shop_assignments(
        year_month="2026-03",
        employee_code=None,
        shop_id=None,
        platform_code=None,
        status=None,
        page=1,
        page_size=20,
        db=dim_shops_core_read_session,
    )

    assert response["data"]["items"][0].shop_name == "Authoritative Shop"
