import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, DimUser, EmployeeTask, EmployeeTaskLog, EmployeeTaskParticipant


@pytest_asyncio.fixture
async def employee_task_route_session():
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
                DimUser(user_id=3, username="cc", email="cc@example.com", password_hash="x", status="active", is_active=True),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def employee_task_async_client(employee_task_route_session):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        def __init__(self, user_id: int):
            self.user_id = user_id
            self.username = "owner"
            self.is_active = True
            self.is_superuser = True
            self.roles = []

    async def override_get_async_db():
        yield employee_task_route_session

    async def override_current_user():
        return MockUser(1)

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def employee_task_async_client_other_user(employee_task_route_session):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        def __init__(self, user_id: int):
            self.user_id = user_id
            self.username = "other"
            self.is_active = True
            self.is_superuser = False
            self.roles = []

    async def override_get_async_db():
        yield employee_task_route_session

    async def override_current_user():
        return MockUser(99)

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seeded_employee_task_data(employee_task_route_session):
    from backend.services.employee_task_service import EmployeeTaskService

    service = EmployeeTaskService(employee_task_route_session)
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
        collaborator_user_ids=[3],
    )


@pytest.mark.asyncio
async def test_employee_task_list_endpoint_returns_owner_scope(
    employee_task_async_client,
    seeded_employee_task_data,
):
    response = await employee_task_async_client.get("/api/employee-tasks?scope=owner")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"][0]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_employee_task_detail_endpoint_returns_timeline(
    employee_task_async_client,
    seeded_employee_task_data,
):
    response = await employee_task_async_client.get("/api/employee-tasks/task-1")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "task-1"
    assert payload["timeline"][0]["action"] == "created"


@pytest.mark.asyncio
async def test_employee_task_detail_endpoint_denies_unrelated_user(
    employee_task_async_client_other_user,
    seeded_employee_task_data,
):
    response = await employee_task_async_client_other_user.get("/api/employee-tasks/task-1")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_employee_task_start_and_submit_endpoints(
    employee_task_async_client,
    seeded_employee_task_data,
):
    start_response = await employee_task_async_client.post("/api/employee-tasks/task-1/start")
    submit_response = await employee_task_async_client.post(
        "/api/employee-tasks/task-1/submit",
        json={
            "completion_payload": {"month": "2026-04", "amount": 1200},
            "result_comment": "done",
            "requires_confirmation": True,
        },
    )

    assert start_response.status_code == 200
    assert submit_response.status_code == 200
    assert submit_response.json()["data"]["status"] == "pending_confirmation"


@pytest.mark.asyncio
async def test_employee_task_collaborator_comment_endpoint(
    employee_task_route_session,
    seeded_employee_task_data,
):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        user_id = 3
        username = "collab"
        is_active = True
        is_superuser = False
        roles = []

    async def override_get_async_db():
        yield employee_task_route_session

    async def override_current_user():
        return MockUser()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/employee-tasks/task-1/comment",
            json={"comment": "collaborator note"},
        )

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["data"]["timeline"][-1]["action"] == "append_comment"


@pytest.mark.asyncio
async def test_employee_task_collaborator_submit_still_denied(
    employee_task_route_session,
    seeded_employee_task_data,
):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        user_id = 3
        username = "collab"
        is_active = True
        is_superuser = False
        roles = []

    async def override_get_async_db():
        yield employee_task_route_session

    async def override_current_user():
        return MockUser()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/employee-tasks/task-1/submit",
            json={
                "completion_payload": {"amount": 500},
                "result_comment": "collab submit",
                "requires_confirmation": False,
            },
        )

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
