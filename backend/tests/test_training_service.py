import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def training_sqlite_session():
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
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO a_class.employees (id, employee_code, name, status, user_id)
                VALUES (1, 'E1024', '张三', 'active', 1)
                """
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_training_service_persists_program_assignment_and_result(training_sqlite_session):
    from backend.services.training_service import TrainingService

    service = TrainingService(training_sqlite_session)

    program = await service.create_program(
        {
            "name": "ERP 操作培训第一期",
            "category": "入职培训",
            "target_role": "新员工",
            "external_platform": "飞书",
            "completion_rule": "完成全部课程并通过考试",
            "learning_url": "https://feishu.example.com/course/erp",
            "exam_url": "https://feishu.example.com/exam/erp",
            "materials_url": "https://feishu.example.com/docs/erp",
            "status": "进行中",
        }
    )

    assignment = await service.create_assignment(
        {
            "employee_name": "张三",
            "employee_code": "E1024",
            "department": "运营部",
            "role_name": "运营专员",
            "program_name": program["name"],
            "learning_status": "待学习",
            "current_status": "待学习",
            "due_date": "2026-04-22",
            "supervisor_name": "李经理",
            "note": "",
        }
    )

    updated = await service.update_result(
        assignment["assignment_id"],
        {
            "exam_score": 88,
            "current_status": "已通过",
            "note": "补考通过",
        },
    )

    overview = await service.get_overview()
    results = await service.list_results()

    assert program["program_id"] is not None
    assert program["learning_url"].startswith("https://")
    assert program["exam_url"].startswith("https://")
    assert program["materials_url"].startswith("https://")
    assert assignment["assignment_id"] is not None
    assert updated["exam_score"] == 88
    assert overview["summary"]["passed_count"] == 1
    assert results["items"][0]["current_status"] == "已通过"


@pytest.mark.asyncio
async def test_training_service_reads_persisted_rows_across_service_instances(training_sqlite_session):
    from backend.services.training_service import TrainingService

    first_service = TrainingService(training_sqlite_session)
    await first_service.create_program(
        {
            "name": "客服岗位认证 V1",
            "category": "岗位认证",
            "target_role": "客服专员",
            "external_platform": "飞书",
            "completion_rule": "课程完成 + 理论考试",
            "learning_url": "https://feishu.example.com/course/cs",
            "exam_url": "https://feishu.example.com/exam/cs",
            "materials_url": "https://feishu.example.com/docs/cs",
            "status": "待上线",
        }
    )

    second_service = TrainingService(training_sqlite_session)
    programs = await second_service.list_programs()

    assert any(item["name"] == "客服岗位认证 V1" for item in programs["items"])


@pytest.mark.asyncio
async def test_training_assignment_creates_employee_task_when_employee_has_user(training_sqlite_session):
    from sqlalchemy import select

    from backend.services.training_service import TrainingService
    from modules.core.db import Notification

    service = TrainingService(training_sqlite_session)
    await service.create_program(
        {
            "name": "ERP 操作培训第一期",
            "category": "入职培训",
            "target_role": "新员工",
            "external_platform": "飞书",
            "completion_rule": "完成全部课程并通过考试",
            "learning_url": "https://feishu.example.com/course/erp",
            "exam_url": "https://feishu.example.com/exam/erp",
            "materials_url": "https://feishu.example.com/docs/erp",
            "status": "进行中",
        }
    )

    assignment = await service.create_assignment(
        {
            "employee_name": "张三",
            "employee_code": "E1024",
            "department": "运营部",
            "role_name": "运营专员",
            "program_name": "ERP 操作培训第一期",
            "learning_status": "待学习",
            "current_status": "待学习",
            "due_date": "2026-04-22",
            "supervisor_name": "李经理",
            "note": "",
        }
    )

    assert assignment["task_id"]

    notification_rows = await training_sqlite_session.execute(select(Notification))
    notifications = notification_rows.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].notification_type == "task_assigned"
