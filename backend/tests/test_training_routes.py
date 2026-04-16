import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def training_pilot_route_session():
    from modules.core.db import (
        Base,
        DimUser,
        Employee,
        EmployeeTask,
        EmployeeTaskLog,
        EmployeeTaskParticipant,
        Notification,
        TrainingAssignment,
        TrainingFeishuConfig,
        TrainingProgram,
        TrainingResult,
    )

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[
                    DimUser.__table__,
                    Employee.__table__,
                    EmployeeTask.__table__,
                    EmployeeTaskLog.__table__,
                    EmployeeTaskParticipant.__table__,
                    Notification.__table__,
                    TrainingFeishuConfig.__table__,
                    TrainingProgram.__table__,
                    TrainingAssignment.__table__,
                    TrainingResult.__table__,
                ],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            DimUser(
                user_id=1,
                username="training-admin",
                email="training-admin@example.com",
                password_hash="x",
                status="active",
                is_active=True,
                is_superuser=True,
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO a_class.employees (id, employee_code, name, status, user_id)
                VALUES (1, 'E1024', 'Zhang San', 'active', 1)
                """
            )
        )
        await session.commit()

        from backend.services.training_service import TrainingService

        service = TrainingService(session)
        await service.create_program(
            {
                "name": "ERP Operation Training Phase 1",
                "category": "Onboarding",
                "target_role": "New Employee",
                "external_platform": "Feishu",
                "completion_rule": "Complete all courses and pass the exam",
                "learning_url": "https://feishu.example.com/course/erp",
                "exam_url": "https://feishu.example.com/exam/erp",
                "materials_url": "https://feishu.example.com/docs/erp",
                "status": "Active",
            }
        )
        await service.create_assignment(
            {
                "employee_name": "Zhang San",
                "employee_code": "E1024",
                "department": "Operations",
                "role_name": "Operator",
                "program_name": "ERP Operation Training Phase 1",
                "learning_status": "Pending",
                "current_status": "Pending",
                "due_date": "2026-04-22",
                "supervisor_name": "Li Manager",
                "note": "",
            }
        )
        await service.update_result(
            "assign-001",
            {
                "exam_score": 86,
                "current_status": "已通过",
                "note": "Initial completion",
            },
        )
        yield session

    await engine.dispose()


def _build_mock_role(role_code: str):
    class MockRole:
        def __init__(self, code: str):
            self.role_code = code
            self.role_name = code

    return MockRole(role_code)


async def _build_client(session, *, user_id: int, username: str, role_code: str, employee_code: str, is_superuser: bool = False):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    class MockUser:
        def __init__(self):
            self.user_id = user_id
            self.username = username
            self.is_active = True
            self.is_superuser = is_superuser
            self.roles = [_build_mock_role(role_code)]
            self.employee_code = employee_code

    async def override_current_user():
        return MockUser()

    async def override_get_async_db():
        yield session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://localhost")
    return app, client


@pytest_asyncio.fixture
async def training_admin_async_client(training_pilot_route_session):
    app, client = await _build_client(
        training_pilot_route_session,
        user_id=1,
        username="training-admin",
        role_code="admin",
        employee_code="E1024",
        is_superuser=True,
    )
    async with client:
        yield client
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_async_db, None)


@pytest_asyncio.fixture
async def training_manager_async_client(training_pilot_route_session):
    app, client = await _build_client(
        training_pilot_route_session,
        user_id=2,
        username="manager",
        role_code="manager",
        employee_code="E2000",
    )
    async with client:
        yield client
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_async_db, None)


@pytest_asyncio.fixture
async def training_operator_self_async_client(training_pilot_route_session):
    app, client = await _build_client(
        training_pilot_route_session,
        user_id=3,
        username="operator-self",
        role_code="operator",
        employee_code="E1024",
    )
    async with client:
        yield client
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_async_db, None)


@pytest_asyncio.fixture
async def training_operator_other_async_client(training_pilot_route_session):
    app, client = await _build_client(
        training_pilot_route_session,
        user_id=4,
        username="operator-other",
        role_code="operator",
        employee_code="E9999",
    )
    async with client:
        yield client
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.asyncio
async def test_training_overview_returns_summary_and_items(training_admin_async_client):
    response = await training_admin_async_client.get("/api/training/overview")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["module_name"] == "培训管理"
    assert payload["summary"]["total_count"] >= 1
    assert payload["summary"]["passed_count"] >= 1
    assert len(payload["items"]) >= 1


@pytest.mark.asyncio
async def test_training_overview_includes_common_status_buckets(training_admin_async_client):
    response = await training_admin_async_client.get("/api/training/overview")

    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    for key in (
        "total_count",
        "pending_count",
        "studying_count",
        "pending_exam_count",
        "passed_count",
        "failed_count",
        "overdue_count",
    ):
        assert key in summary


@pytest.mark.asyncio
async def test_training_programs_and_my_overview_routes_exist(training_admin_async_client):
    programs_response = await training_admin_async_client.get("/api/training/programs")
    my_overview_response = await training_admin_async_client.get("/api/training/my-overview")

    assert programs_response.status_code == 200
    assert my_overview_response.status_code == 200
    assert len(programs_response.json()["data"]["items"]) >= 1
    assert my_overview_response.json()["data"]["employee_name"]


@pytest.mark.asyncio
async def test_training_assignment_detail_route_returns_assignment_detail(training_admin_async_client):
    response = await training_admin_async_client.get("/api/training/assignments/assign-001")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["assignment_id"] == "assign-001"
    assert payload["employee_name"]
    assert payload["program_name"]
    assert payload["learning_url"].startswith("https://")
    assert payload["exam_url"].startswith("https://")


@pytest.mark.asyncio
async def test_training_program_can_be_created(training_admin_async_client):
    response = await training_admin_async_client.post(
        "/api/training/programs",
        json={
            "name": "Warehouse Certification V1",
            "category": "Role Certification",
            "target_role": "Warehouse Specialist",
            "external_platform": "Feishu",
            "completion_rule": "Course complete + theory exam",
            "learning_url": "https://feishu.example.com/course/warehouse",
            "exam_url": "https://feishu.example.com/exam/warehouse",
            "materials_url": "https://feishu.example.com/docs/warehouse",
            "status": "Pending",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "Warehouse Certification V1"
    assert payload["category"] == "Role Certification"
    assert payload["materials_url"].startswith("https://")


@pytest.mark.asyncio
async def test_training_assignment_can_be_created(training_admin_async_client):
    response = await training_admin_async_client.post(
        "/api/training/assignments",
        json={
            "employee_name": "Wu Jiu",
            "employee_code": "E1030",
            "department": "Operations",
            "role_name": "Operator",
            "program_name": "ERP Operation Training Phase 1",
            "learning_status": "Pending",
            "current_status": "Pending",
            "due_date": "2026-04-22",
            "supervisor_name": "Li Manager",
            "note": "New assignment",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["employee_code"] == "E1030"
    assert payload["program_name"] == "ERP Operation Training Phase 1"
    assert payload["task_id"] is None


@pytest.mark.asyncio
async def test_training_result_can_be_updated(training_admin_async_client):
    response = await training_admin_async_client.put(
        "/api/training/results/assign-001",
        json={
            "exam_score": 88,
            "current_status": "已通过",
            "note": "Retake passed",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["assignment_id"] == "assign-001"
    assert payload["exam_score"] == 88
    assert payload["current_status"] == "已通过"


@pytest.mark.asyncio
async def test_training_management_routes_forbid_operator(training_operator_other_async_client):
    response = await training_operator_other_async_client.get("/api/training/overview")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_training_assignment_detail_allows_owner(training_operator_self_async_client):
    owner_response = await training_operator_self_async_client.get("/api/training/assignments/assign-001")

    assert owner_response.status_code == 200


@pytest.mark.asyncio
async def test_training_assignment_detail_denies_other_operator(training_operator_other_async_client):
    other_response = await training_operator_other_async_client.get("/api/training/assignments/assign-001")

    assert other_response.status_code == 403


@pytest.mark.asyncio
async def test_training_assignment_detail_allows_manager(training_manager_async_client):
    manager_response = await training_manager_async_client.get("/api/training/assignments/assign-001")

    assert manager_response.status_code == 200


@pytest.mark.asyncio
async def test_training_mutation_routes_forbid_operator(training_operator_self_async_client):
    create_program_response = await training_operator_self_async_client.post(
        "/api/training/programs",
        json={
            "name": "Forbidden Program",
            "category": "Role Certification",
            "target_role": "Operator",
            "external_platform": "Feishu",
            "completion_rule": "Course complete",
            "status": "Pending",
        },
    )
    update_result_response = await training_operator_self_async_client.put(
        "/api/training/results/assign-001",
        json={
            "exam_score": 99,
            "current_status": "已通过",
            "note": "Operator should not change result",
        },
    )

    assert create_program_response.status_code == 403
    assert update_result_response.status_code == 403
