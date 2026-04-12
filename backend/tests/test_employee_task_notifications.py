import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.schemas.notification import NotificationType
from modules.core.db import Base, DimUser, Notification


@pytest_asyncio.fixture
async def employee_task_notification_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[DimUser.__table__, Notification.__table__],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            DimUser(
                user_id=1,
                username="owner",
                email="owner@example.com",
                password_hash="x",
                status="active",
                is_active=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


def test_notification_type_includes_employee_task_variants():
    assert NotificationType.TASK_ASSIGNED.value == "task_assigned"
    assert NotificationType.TASK_DUE_SOON.value == "task_due_soon"
    assert NotificationType.TASK_OVERDUE.value == "task_overdue"
    assert NotificationType.TASK_RETURNED.value == "task_returned"
    assert NotificationType.TASK_NUDGED.value == "task_nudged"


@pytest.mark.asyncio
async def test_employee_task_notification_helper_creates_assignment_notification(
    employee_task_notification_session,
):
    from backend.services.employee_task_notifications import notify_task_assigned

    notification = await notify_task_assigned(
        db=employee_task_notification_session,
        recipient_id=1,
        task_id="task-1",
        task_type="monthly_cost_entry",
        source_module="expense-management",
        source_record_type="expense",
        source_record_id="exp-1",
        title="New task assigned",
        content="Please fill the monthly cost record.",
    )
    await employee_task_notification_session.commit()

    assert notification.notification_type == "task_assigned"
    assert notification.extra_data["task_id"] == "task-1"
    assert notification.extra_data["target_route"] == "/my-tasks/task-1"

    result = await employee_task_notification_session.execute(select(Notification))
    rows = result.scalars().all()
    assert len(rows) == 1
