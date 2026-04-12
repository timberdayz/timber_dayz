import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    Base,
    DimPlatform,
    DimShop,
    DimUser,
    Employee,
    EmployeeShopAssignment,
    EmployeeTask,
    EmployeeTaskLog,
    EmployeeTaskParticipant,
)


@pytest_asyncio.fixture
async def employee_task_source_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[
                    DimPlatform.__table__,
                    DimShop.__table__,
                    DimUser.__table__,
                    Employee.__table__,
                    EmployeeShopAssignment.__table__,
                    EmployeeTask.__table__,
                    EmployeeTaskLog.__table__,
                    EmployeeTaskParticipant.__table__,
                ],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(DimPlatform(platform_code="shopee", name="Shopee"))
        session.add(DimShop(platform_code="shopee", shop_id="shop-1", shop_name="Shop 1"))
        session.add_all(
            [
                DimUser(user_id=1, username="sup1", email="sup1@example.com", password_hash="x", status="active", is_active=True),
                DimUser(user_id=2, username="worker", email="worker@example.com", password_hash="x", status="active", is_active=True),
            ]
        )
        session.add_all(
            [
                Employee(id=1, employee_code="EMP001", name="Supervisor 1", user_id=1, status="active"),
                Employee(id=2, employee_code="EMP002", name="Operator 1", user_id=2, status="active"),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_shop_supervisor_owner_returns_user_id(employee_task_source_session):
    from backend.services.employee_task_sources import resolve_shop_supervisor_user_id

    employee_task_source_session.add(
        EmployeeShopAssignment(
            id=1,
            year_month="2026-04",
            employee_code="EMP001",
            platform_code="shopee",
            shop_id="shop-1",
            role="supervisor",
            commission_ratio=0.1,
            status="active",
        )
    )
    await employee_task_source_session.commit()

    owner_user_id = await resolve_shop_supervisor_user_id(
        employee_task_source_session,
        year_month="2026-04",
        platform_code="shopee",
        shop_id="shop-1",
    )

    assert owner_user_id == 1


@pytest.mark.asyncio
async def test_resolve_shop_supervisor_owner_rejects_missing_supervisor(employee_task_source_session):
    from backend.services.employee_task_sources import resolve_shop_supervisor_user_id

    with pytest.raises(ValueError, match="supervisor"):
        await resolve_shop_supervisor_user_id(
            employee_task_source_session,
            year_month="2026-04",
            platform_code="shopee",
            shop_id="shop-1",
        )


@pytest.mark.asyncio
async def test_resolve_shop_supervisor_owner_rejects_multiple_supervisors(employee_task_source_session):
    from backend.services.employee_task_sources import resolve_shop_supervisor_user_id

    employee_task_source_session.add(DimUser(user_id=3, username="sup2", email="sup2@example.com", password_hash="x", status="active", is_active=True))
    employee_task_source_session.add(Employee(id=3, employee_code="EMP003", name="Supervisor 2", user_id=3, status="active"))
    employee_task_source_session.add_all(
        [
            EmployeeShopAssignment(
                id=1,
                year_month="2026-04",
                employee_code="EMP001",
                platform_code="shopee",
                shop_id="shop-1",
                role="supervisor",
                commission_ratio=0.1,
                status="active",
            ),
            EmployeeShopAssignment(
                id=2,
                year_month="2026-04",
                employee_code="EMP003",
                platform_code="shopee",
                shop_id="shop-1",
                role="supervisor",
                commission_ratio=0.1,
                status="active",
            ),
        ]
    )
    await employee_task_source_session.commit()

    with pytest.raises(ValueError, match="multiple"):
        await resolve_shop_supervisor_user_id(
            employee_task_source_session,
            year_month="2026-04",
            platform_code="shopee",
            shop_id="shop-1",
        )


@pytest.mark.asyncio
async def test_sync_monthly_cost_entry_task_creates_owner_scoped_task(employee_task_source_session):
    from backend.services.employee_task_sources import sync_monthly_cost_entry_task

    employee_task_source_session.add(
        EmployeeShopAssignment(
            id=1,
            year_month="2026-04",
            employee_code="EMP001",
            platform_code="shopee",
            shop_id="shop-1",
            role="supervisor",
            commission_ratio=0.1,
            status="active",
        )
    )
    await employee_task_source_session.commit()

    payload = await sync_monthly_cost_entry_task(
        employee_task_source_session,
        year_month="2026-04",
        platform_code="shopee",
        shop_id="shop-1",
        created_by=1,
    )

    assert payload["task_type"] == "monthly_cost_entry"
    assert payload["owner_user_id"] == 1
    assert payload["source_module"] == "expense-management"

    rows = await employee_task_source_session.execute(select(EmployeeTask))
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_sync_performance_confirmation_task_targets_employee_user(employee_task_source_session):
    from backend.services.employee_task_sources import sync_performance_confirmation_task

    payload = await sync_performance_confirmation_task(
        employee_task_source_session,
        year_month="2026-04",
        employee_code="EMP002",
        created_by=1,
    )

    assert payload["task_type"] == "performance_confirmation"
    assert payload["owner_user_id"] == 2
    assert payload["source_module"] == "performance-management"


@pytest.mark.asyncio
async def test_sync_monthly_cost_entry_task_rejects_owner_without_required_permission(employee_task_source_session):
    from backend.services.employee_task_sources import sync_monthly_cost_entry_task

    employee_task_source_session.add(
        EmployeeShopAssignment(
            id=1,
            year_month="2026-04",
            employee_code="EMP001",
            platform_code="shopee",
            shop_id="shop-1",
            role="supervisor",
            commission_ratio=0.1,
            status="active",
        )
    )
    await employee_task_source_session.commit()

    with pytest.raises(ValueError, match="permission"):
        await sync_monthly_cost_entry_task(
            employee_task_source_session,
            year_month="2026-04",
            platform_code="shopee",
            shop_id="shop-1",
            created_by=1,
            owner_permissions={"my-tasks"},
        )


@pytest.mark.asyncio
async def test_sync_performance_confirmation_task_rejects_owner_without_required_permission(employee_task_source_session):
    from backend.services.employee_task_sources import sync_performance_confirmation_task

    with pytest.raises(ValueError, match="permission"):
        await sync_performance_confirmation_task(
            employee_task_source_session,
            year_month="2026-04",
            employee_code="EMP002",
            created_by=1,
            owner_permissions={"expense-management"},
        )
