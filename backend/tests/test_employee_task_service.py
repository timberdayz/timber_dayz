import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, DimUser, EmployeeTask, EmployeeTaskLog, EmployeeTaskParticipant


@pytest_asyncio.fixture
async def employee_task_sqlite_session():
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
                DimUser(
                    user_id=1,
                    username="owner",
                    email="owner@example.com",
                    password_hash="x",
                    status="active",
                    is_active=True,
                ),
                DimUser(
                    user_id=2,
                    username="creator",
                    email="creator@example.com",
                    password_hash="x",
                    status="active",
                    is_active=True,
                ),
                DimUser(
                    user_id=3,
                    username="cc",
                    email="cc@example.com",
                    password_hash="x",
                    status="active",
                    is_active=True,
                ),
                DimUser(
                    user_id=4,
                    username="helper",
                    email="helper@example.com",
                    password_hash="x",
                    status="active",
                    is_active=True,
                ),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_employee_task_service_creates_task_with_participants(employee_task_sqlite_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_sqlite_session)

    payload = await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
        cc_user_ids=[3],
        collaborator_user_ids=[4],
    )

    assert payload["task_id"] == "task-1"
    assert payload["owner_user_id"] == 1
    assert payload["cc_user_ids"] == [3]
    assert payload["collaborator_user_ids"] == [4]
    assert payload["status"] == "pending"

    task_rows = await employee_task_sqlite_session.execute(select(EmployeeTask))
    participant_rows = await employee_task_sqlite_session.execute(select(EmployeeTaskParticipant))
    log_rows = await employee_task_sqlite_session.execute(select(EmployeeTaskLog))

    assert len(task_rows.scalars().all()) == 1
    assert len(participant_rows.scalars().all()) == 2
    assert len(log_rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_employee_task_service_lists_owner_and_cc_views(employee_task_sqlite_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_sqlite_session)

    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
        cc_user_ids=[3],
    )

    owner_items = await service.list_tasks_for_user(user_id=1, scope="owner")
    initiated_items = await service.list_tasks_for_user(user_id=2, scope="initiated")
    cc_items = await service.list_tasks_for_user(user_id=3, scope="cc")

    assert [item["task_id"] for item in owner_items] == ["task-1"]
    assert [item["task_id"] for item in initiated_items] == ["task-1"]
    assert [item["task_id"] for item in cc_items] == ["task-1"]


@pytest.mark.asyncio
async def test_employee_task_service_rejects_missing_owner(employee_task_sqlite_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_sqlite_session)

    with pytest.raises(ValueError, match="owner"):
        await service.create_task(
            task_id="task-1",
            task_type="monthly_cost_entry",
            task_category="execution",
            title="Fill monthly cost",
            owner_user_id=None,
            created_by=2,
            source_type="system",
            source_module="expense-management",
        )


@pytest.mark.asyncio
async def test_employee_task_service_owner_flow_updates_status_and_logs(employee_task_sqlite_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_sqlite_session)

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

    await service.start_task("task-1", actor_user_id=1)
    await service.submit_task_result(
        "task-1",
        actor_user_id=1,
        completion_payload={"month": "2026-04", "amount": 1200},
        result_comment="done",
        requires_confirmation=True,
    )

    detail = await service.get_task_detail("task-1")

    assert detail["status"] == "pending_confirmation"
    assert detail["result_comment"] == "done"
    assert detail["completion_payload"]["amount"] == 1200
    assert [entry["action"] for entry in detail["timeline"]] == [
        "created",
        "started",
        "submitted",
    ]
