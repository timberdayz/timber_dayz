import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, DimUser, EmployeeTask, EmployeeTaskLog, EmployeeTaskParticipant


@pytest_asyncio.fixture
async def employee_task_admin_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[
                    DimUser.__table__,
                    EmployeeTask.__table__,
                    EmployeeTaskLog.__table__,
                    EmployeeTaskParticipant.__table__,
                ],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                DimUser(user_id=1, username="owner", email="owner@example.com", password_hash="x", status="active", is_active=True),
                DimUser(user_id=2, username="creator", email="creator@example.com", password_hash="x", status="active", is_active=True),
                DimUser(user_id=9, username="admin", email="admin@example.com", password_hash="x", status="active", is_active=True, is_superuser=True),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_can_reassign_task_owner(employee_task_admin_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_admin_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
    )

    detail = await service.reassign_task(
        "task-1",
        actor_user_id=9,
        new_owner_user_id=2,
        reason="owner changed",
    )

    assert detail["owner_user_id"] == 2
    assert detail["timeline"][-1]["action"] == "reassign_task"


@pytest.mark.asyncio
async def test_admin_can_take_over_task(employee_task_admin_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_admin_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
    )

    detail = await service.take_over_task(
        "task-1",
        actor_user_id=9,
        reason="admin takeover",
    )

    assert detail["owner_user_id"] == 9
    assert detail["timeline"][-1]["action"] == "takeover_task"


@pytest.mark.asyncio
async def test_admin_can_force_close_task(employee_task_admin_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_admin_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
    )

    detail = await service.force_close_task(
        "task-1",
        actor_user_id=9,
        reason="task invalidated",
    )

    assert detail["status"] == "closed"
    assert detail["timeline"][-1]["action"] == "force_close_task"
