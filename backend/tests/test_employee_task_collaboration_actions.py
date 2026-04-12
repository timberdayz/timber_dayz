import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, DimUser, EmployeeTask, EmployeeTaskLog, EmployeeTaskParticipant


@pytest_asyncio.fixture
async def employee_task_collab_session():
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
                DimUser(user_id=3, username="collab", email="collab@example.com", password_hash="x", status="active", is_active=True),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_collaborator_can_append_comment(employee_task_collab_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_collab_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
        collaborator_user_ids=[3],
    )

    detail = await service.append_task_comment(
        "task-1",
        actor_user_id=3,
        comment="supporting note from collaborator",
    )

    assert detail["status"] == "pending"
    assert detail["timeline"][-1]["action"] == "append_comment"


@pytest.mark.asyncio
async def test_collaborator_can_append_structured_data(employee_task_collab_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_collab_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
        collaborator_user_ids=[3],
    )

    detail = await service.append_task_structured_data(
        "task-1",
        actor_user_id=3,
        payload={"draft_amount": 500},
    )

    assert detail["timeline"][-1]["action"] == "append_structured_data"
    assert detail["timeline"][-1]["details_json"]["draft_amount"] == 500


@pytest.mark.asyncio
async def test_collaborator_may_not_submit_final_result(employee_task_collab_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_collab_session)
    await service.create_task(
        task_id="task-1",
        task_type="monthly_cost_entry",
        task_category="execution",
        title="Fill monthly cost",
        owner_user_id=1,
        created_by=2,
        source_type="system",
        source_module="expense-management",
        collaborator_user_ids=[3],
    )

    with pytest.raises(ValueError, match="Only the task owner"):
        await service.submit_task_result(
            "task-1",
            actor_user_id=3,
            completion_payload={"amount": 500},
            result_comment="collaborator submit",
        )
