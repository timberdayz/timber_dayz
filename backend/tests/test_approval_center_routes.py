import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    ApprovalActionLog,
    ApprovalInstance,
    ApprovalStep,
    ApprovalTemplate,
    Base,
    DimUser,
    EmployeeTask,
    EmployeeTaskLog,
    EmployeeTaskParticipant,
)


@pytest_asyncio.fixture
async def approval_center_route_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[
                    DimUser.__table__,
                    ApprovalTemplate.__table__,
                    ApprovalInstance.__table__,
                    ApprovalStep.__table__,
                    ApprovalActionLog.__table__,
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
                DimUser(user_id=1, username="applicant", email="applicant@example.com", password_hash="x", status="active", is_active=True),
                DimUser(user_id=2, username="approver", email="approver@example.com", password_hash="x", status="active", is_active=True),
                ApprovalTemplate(
                    template_code="leave_request_approval",
                    template_name="Leave Request Approval",
                    business_type="leave_request",
                    enabled=True,
                    target_route="/approval-center/leave",
                    approval_mode="single",
                    form_schema={"fields": ["start_date", "end_date", "reason"]},
                ),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def approval_center_async_client(approval_center_route_session):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        user_id = 1
        username = "applicant"
        is_active = True
        is_superuser = False
        roles = []

    async def override_get_async_db():
        yield approval_center_route_session

    async def override_current_user():
        return MockUser()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def approval_center_async_client_approver(approval_center_route_session):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    class MockUser:
        user_id = 2
        username = "approver"
        is_active = True
        is_superuser = False
        roles = []

    async def override_get_async_db():
        yield approval_center_route_session

    async def override_current_user():
        return MockUser()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seeded_approval_data(approval_center_route_session):
    from backend.services.approval_center_service import ApprovalCenterService

    service = ApprovalCenterService(approval_center_route_session)
    await service.submit_approval(
        template_code="leave_request_approval",
        applicant_user_id=1,
        business_key="leave:2026-04:1",
        form_payload={"start_date": "2026-04-10", "end_date": "2026-04-11", "reason": "travel"},
        approver_user_id=2,
    )


@pytest.mark.asyncio
async def test_approval_center_requests_endpoint_returns_items(
    approval_center_async_client,
    seeded_approval_data,
):
    response = await approval_center_async_client.get("/api/approval-center/requests")

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["approval_id"].startswith("approval:")


@pytest.mark.asyncio
async def test_approval_center_detail_endpoint_returns_steps(
    approval_center_async_client,
    seeded_approval_data,
):
    response = await approval_center_async_client.get("/api/approval-center/approval:leave_request_approval:leave:2026-04:1")

    assert response.status_code == 200
    assert response.json()["data"]["steps"][0]["step_order"] == 1


@pytest.mark.asyncio
async def test_approval_center_approve_endpoint(
    approval_center_async_client_approver,
    seeded_approval_data,
):
    response = await approval_center_async_client_approver.post(
        "/api/approval-center/approval:leave_request_approval:leave:2026-04:1/approve",
        json={"comment": "approved"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "approved"


@pytest.mark.asyncio
async def test_approval_center_withdraw_endpoint(
    approval_center_async_client,
    seeded_approval_data,
):
    response = await approval_center_async_client.post(
        "/api/approval-center/approval:leave_request_approval:leave:2026-04:1/withdraw",
        json={"comment": "withdraw"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
