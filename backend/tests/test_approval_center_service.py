import pytest
import pytest_asyncio
from sqlalchemy import select, text
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
async def approval_center_session():
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


@pytest.mark.asyncio
async def test_submit_approval_creates_instance_step_and_task_projection(approval_center_session):
    from backend.services.approval_center_service import ApprovalCenterService

    service = ApprovalCenterService(approval_center_session)
    detail = await service.submit_approval(
        template_code="leave_request_approval",
        applicant_user_id=1,
        business_key="leave:2026-04:1",
        form_payload={"start_date": "2026-04-10", "end_date": "2026-04-11", "reason": "travel"},
        approver_user_id=2,
    )

    assert detail["status"] == "submitted"
    assert detail["current_step"] == 1

    tasks = await approval_center_session.execute(select(EmployeeTask))
    assert len(tasks.scalars().all()) == 1


@pytest.mark.asyncio
async def test_approve_step_advances_and_closes_previous_projection(approval_center_session):
    from backend.services.approval_center_service import ApprovalCenterService

    service = ApprovalCenterService(approval_center_session)
    detail = await service.submit_approval(
        template_code="leave_request_approval",
        applicant_user_id=1,
        business_key="leave:2026-04:1",
        form_payload={"start_date": "2026-04-10", "end_date": "2026-04-11", "reason": "travel"},
        approver_user_id=2,
    )

    approved = await service.approve_step(detail["approval_id"], actor_user_id=2, comment="ok")

    assert approved["status"] == "approved"
    assert approved["timeline"][-1]["action_type"] == "approve"


@pytest.mark.asyncio
async def test_reject_step_finishes_workflow(approval_center_session):
    from backend.services.approval_center_service import ApprovalCenterService

    service = ApprovalCenterService(approval_center_session)
    detail = await service.submit_approval(
        template_code="leave_request_approval",
        applicant_user_id=1,
        business_key="leave:2026-04:1",
        form_payload={"start_date": "2026-04-10", "end_date": "2026-04-11", "reason": "travel"},
        approver_user_id=2,
    )

    rejected = await service.reject_step(detail["approval_id"], actor_user_id=2, comment="not allowed")

    assert rejected["status"] == "rejected"
    assert rejected["timeline"][-1]["action_type"] == "reject"


@pytest.mark.asyncio
async def test_withdraw_approval_closes_pending_projection(approval_center_session):
    from backend.services.approval_center_service import ApprovalCenterService

    service = ApprovalCenterService(approval_center_session)
    detail = await service.submit_approval(
        template_code="leave_request_approval",
        applicant_user_id=1,
        business_key="leave:2026-04:1",
        form_payload={"start_date": "2026-04-10", "end_date": "2026-04-11", "reason": "travel"},
        approver_user_id=2,
    )

    withdrawn = await service.withdraw_approval(detail["approval_id"], actor_user_id=1, comment="withdrawn")

    assert withdrawn["status"] == "cancelled"
    assert withdrawn["timeline"][-1]["action_type"] == "withdraw"
