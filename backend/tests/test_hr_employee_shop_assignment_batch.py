"""批量归属端点（create / update / delete）的契约守护。

为什么要有这个端点
------------------
「员工店铺归属」一行 = 人 × 平台 × 店 × 月 × 提成比。
现实里同一个人常常要挂到好几家店、同一月的多家店要一起调比例 ——
逐条调单条接口既慢，又容易中途失败留下半截数据。
批量端点把「同一个动作重复多次」压成一次提交：

* 整批**一个事务**：成功项一起提交；
* **单项失败只跳过该项**：写进 ``failed`` 并说明原因，其余项照常成功；
* 校验口径与单条接口**完全一致**（员工存在 / 店铺已同步 / 不重复挂靠 /
  店铺当月人员提成比例合计 ≤ 100% / 工资月锁）；
* 归属**不再有「角色」** —— 一行只回答「谁在这家店分多少提成」。

事务隔离说明
------------
批量端点内部会 ``commit()``，而 ``pg_session`` 靠「用例结束回滚」做隔离 ⇒
commit 会把数据留在库里串到别的用例。所以这里用 ``pg_database``：
**每个用例独占一个 database**，物理隔离，不依赖回滚。
"""

from types import SimpleNamespace
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.domains.business.routers.hr_commission import (
    batch_employee_shop_assignments,
)
from backend.schemas.hr import (
    EmployeeShopAssignmentBatchItem,
    EmployeeShopAssignmentBatchRequest,
)
from modules.core.db import (
    Base,
    DimPlatform,
    DimShop,
    Employee,
    EmployeeShopAssignment,
)

YEAR_MONTH = "2026-11"
OTHER_MONTH = "2026-12"


@pytest_asyncio.fixture
async def assignment_session(pg_database):
    """每个用例独占一个 database（见模块说明：批量端点会 commit）。"""
    async with pg_database() as pg:
        async_url = urlunparse(
            urlparse(pg.get_connection_url())._replace(scheme="postgresql+asyncpg")
        )
        engine = create_async_engine(async_url, echo=False)
        async with engine.begin() as conn:
            for schema_name in (
                "core",
                "a_class",
                "b_class",
                "c_class",
                "finance",
                "ops",
                "semantic",
            ):
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            session.add(DimPlatform(platform_code="shopee", name="Shopee"))
            session.add(
                DimShop(platform_code="shopee", shop_id="SHOP-A", shop_name="店铺A")
            )
            session.add(
                DimShop(platform_code="shopee", shop_id="SHOP-B", shop_name="店铺B")
            )
            session.add(Employee(employee_code="EMP001", name="张三", status="active"))
            session.add(Employee(employee_code="EMP002", name="李四", status="active"))
            await session.commit()
            yield session
        await engine.dispose()


def _item(employee_code: str, shop_id: str, ratio: float | None) -> dict:
    return {
        "employee_code": employee_code,
        "platform_code": "shopee",
        "shop_id": shop_id,
        "commission_ratio": ratio,
    }


def _request(mode: str, **kwargs) -> EmployeeShopAssignmentBatchRequest:
    return EmployeeShopAssignmentBatchRequest(
        year_month=kwargs.pop("year_month", YEAR_MONTH),
        mode=mode,
        items=kwargs.pop("items", []),
        assignment_ids=kwargs.pop("assignment_ids", []),
    )


async def _run(session, request):
    return await batch_employee_shop_assignments(
        body=request,
        db=session,
        _current_user=SimpleNamespace(user_id=1),
    )


async def _seed_assignment(session, **kwargs) -> EmployeeShopAssignment:
    record = EmployeeShopAssignment(
        year_month=kwargs.get("year_month", YEAR_MONTH),
        employee_code=kwargs.get("employee_code", "EMP001"),
        platform_code=kwargs.get("platform_code", "shopee"),
        shop_id=kwargs.get("shop_id", "SHOP-A"),
        commission_ratio=kwargs.get("commission_ratio", 0.4),
        target_allocation_ratio=1.0,
        target_allocation_ratio_source="manual",
        status=kwargs.get("status", "active"),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@pytest.mark.asyncio
async def test_batch_create_writes_every_item_and_reports_ids(assignment_session):
    result = await _run(
        assignment_session,
        _request(
            "create",
            items=[
                _item("EMP001", "SHOP-A", 0.15),
                _item("EMP002", "SHOP-B", 0.05),
            ],
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data.summary.total == 2
    assert data.summary.succeeded == 2
    assert data.summary.failed == 0
    assert data.failed == []

    succeeded = {row.employee_code: row for row in data.succeeded}
    assert set(succeeded) == {"EMP001", "EMP002"}
    assert succeeded["EMP001"].id is not None
    assert succeeded["EMP001"].shop_id == "SHOP-A"
    assert succeeded["EMP001"].commission_ratio == 0.15
    assert succeeded["EMP001"].employee_name == "张三"
    assert succeeded["EMP002"].id is not None
    assert succeeded["EMP002"].commission_ratio == 0.05

    rows = (
        (await assignment_session.execute(select(EmployeeShopAssignment)))
        .scalars()
        .all()
    )
    assert {(row.employee_code, row.shop_id) for row in rows} == {
        ("EMP001", "SHOP-A"),
        ("EMP002", "SHOP-B"),
    }


@pytest.mark.asyncio
async def test_batch_create_skips_item_over_shop_ratio_limit_but_keeps_others(
    assignment_session,
):
    """店铺当月人员提成比例合计 ≤ 100%：超限的那条跳过，其余照常成功。"""
    await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.4,
    )

    result = await _run(
        assignment_session,
        _request(
            "create",
            items=[
                _item("EMP002", "SHOP-A", 0.7),  # 0.4 + 0.7 > 100% ⇒ 跳过
                _item("EMP002", "SHOP-B", 0.1),  # 正常
            ],
        ),
    )

    data = result["data"]
    assert data.summary.total == 2
    assert data.summary.succeeded == 1
    assert data.summary.failed == 1

    assert len(data.succeeded) == 1
    assert data.succeeded[0].shop_id == "SHOP-B"
    assert data.succeeded[0].commission_ratio == 0.1

    assert len(data.failed) == 1
    assert "100%" in data.failed[0].reason
    assert "EMP002" in data.failed[0].target
    assert "SHOP-A" in data.failed[0].target

    # 单项失败不得回滚整批：成功的行必须真的落库。
    rows = (
        (await assignment_session.execute(select(EmployeeShopAssignment)))
        .scalars()
        .all()
    )
    assert {(row.employee_code, row.shop_id, row.commission_ratio) for row in rows} == {
        ("EMP001", "SHOP-A", 0.4),
        ("EMP002", "SHOP-B", 0.1),
    }


@pytest.mark.asyncio
async def test_batch_create_skips_duplicate_assignment(assignment_session):
    await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request(
            "create",
            items=[
                _item("EMP001", "SHOP-A", 0.2),  # 重复挂靠 ⇒ 跳过
                _item("EMP002", "SHOP-A", 0.2),  # 正常
            ],
        ),
    )

    data = result["data"]
    assert data.summary.succeeded == 1
    assert data.summary.failed == 1
    assert len(data.failed) == 1
    assert "已关联" in data.failed[0].reason
    assert data.succeeded[0].employee_code == "EMP002"


@pytest.mark.asyncio
async def test_batch_create_skips_unknown_employee(assignment_session):
    result = await _run(
        assignment_session,
        _request("create", items=[_item("EMP999", "SHOP-A", 0.1)]),
    )

    data = result["data"]
    assert data.summary.total == 1
    assert data.summary.succeeded == 0
    assert data.summary.failed == 1
    assert "员工不存在" in data.failed[0].reason
    assert "EMP999" in data.failed[0].target


@pytest.mark.asyncio
async def test_batch_update_changes_commission_ratio(assignment_session):
    record = await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request(
            "update",
            items=[_item("EMP001", "SHOP-A", 0.35)],
            assignment_ids=[record.id],
        ),
    )

    data = result["data"]
    assert data.summary.total == 1
    assert data.summary.succeeded == 1
    assert data.summary.failed == 0
    assert data.succeeded[0].id == record.id
    assert data.succeeded[0].commission_ratio == 0.35

    await assignment_session.refresh(record)
    assert record.commission_ratio == 0.35


@pytest.mark.asyncio
async def test_batch_update_skips_item_over_shop_ratio_limit(assignment_session):
    await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.6,
    )
    target = await _seed_assignment(
        assignment_session,
        employee_code="EMP002",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request(
            "update",
            items=[_item("EMP002", "SHOP-A", 0.5)],  # 0.6 + 0.5 > 100% ⇒ 跳过
            assignment_ids=[target.id],
        ),
    )

    data = result["data"]
    assert data.summary.succeeded == 0
    assert data.summary.failed == 1
    assert "100%" in data.failed[0].reason

    await assignment_session.refresh(target)
    assert target.commission_ratio == 0.1


@pytest.mark.asyncio
async def test_batch_update_rejects_item_not_matching_the_assignment(
    assignment_session,
):
    record = await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request(
            "update",
            items=[_item("EMP002", "SHOP-A", 0.2)],  # 与目标记录不是同一个人
            assignment_ids=[record.id],
        ),
    )

    data = result["data"]
    assert data.summary.succeeded == 0
    assert data.summary.failed == 1
    assert "不匹配" in data.failed[0].reason

    await assignment_session.refresh(record)
    assert record.commission_ratio == 0.1


@pytest.mark.asyncio
async def test_batch_delete_removes_assignment(assignment_session):
    record = await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request("delete", assignment_ids=[record.id]),
    )

    data = result["data"]
    assert data.summary.total == 1
    assert data.summary.succeeded == 1
    assert data.summary.failed == 0
    assert data.succeeded[0].id == record.id
    assert data.succeeded[0].action == "delete"

    rows = (
        (await assignment_session.execute(select(EmployeeShopAssignment)))
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_batch_delete_skips_missing_assignment(assignment_session):
    result = await _run(
        assignment_session,
        _request("delete", assignment_ids=[999999]),
    )

    data = result["data"]
    assert data.summary.total == 1
    assert data.summary.succeeded == 0
    assert data.summary.failed == 1
    assert "不存在" in data.failed[0].reason


@pytest.mark.asyncio
async def test_batch_summary_counts_add_up(assignment_session):
    await _seed_assignment(
        assignment_session,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.4,
    )

    result = await _run(
        assignment_session,
        _request(
            "create",
            items=[
                _item("EMP001", "SHOP-A", 0.1),  # 重复 ⇒ 失败
                _item("EMP002", "SHOP-A", 0.9),  # 0.4 + 0.9 > 100% ⇒ 失败
                _item("EMP002", "SHOP-B", 0.1),  # 成功
                _item("EMP404", "SHOP-B", 0.1),  # 员工不存在 ⇒ 失败
            ],
        ),
    )

    data = result["data"]
    assert data.summary.total == 4
    assert data.summary.succeeded == 1
    assert data.summary.failed == 3
    assert data.summary.total == data.summary.succeeded + data.summary.failed
    assert len(data.succeeded) == 1
    assert len(data.failed) == 3


@pytest.mark.asyncio
async def test_batch_create_accepts_legacy_role_field_in_item(assignment_session):
    """兼容：旧页面仍会带 role ⇒ 必须被忽略，而不是报错。"""
    request = EmployeeShopAssignmentBatchRequest.model_validate(
        {
            "year_month": YEAR_MONTH,
            "mode": "create",
            "items": [
                {
                    "employee_code": "EMP001",
                    "platform_code": "shopee",
                    "shop_id": "SHOP-A",
                    "commission_ratio": 0.1,
                    "role": "supervisor",
                }
            ],
            "assignment_ids": [],
        }
    )

    result = await _run(assignment_session, request)

    assert result["success"] is True
    assert result["data"].summary.succeeded == 1
    assert result["data"].summary.failed == 0


@pytest.mark.asyncio
async def test_batch_rejects_assignment_from_another_month(assignment_session):
    record = await _seed_assignment(
        assignment_session,
        year_month=OTHER_MONTH,
        employee_code="EMP001",
        shop_id="SHOP-A",
        commission_ratio=0.1,
    )

    result = await _run(
        assignment_session,
        _request(
            "delete",
            assignment_ids=[record.id],
            year_month=YEAR_MONTH,
        ),
    )

    data = result["data"]
    assert data.summary.succeeded == 0
    assert data.summary.failed == 1
    assert OTHER_MONTH in data.failed[0].reason

    rows = (
        (await assignment_session.execute(select(EmployeeShopAssignment)))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_batch_endpoint_http_contract(assignment_session):
    """走 HTTP：路由声明的 ``response_model`` 必须能兜住真实响应体。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from backend.dependencies.auth import require_admin
    from backend.models.database import get_async_db
    from backend.domains.business.routers.hr_commission import router

    app = FastAPI()
    # ⚠️ 路由自带前缀 ``/api/hr``（前端 axios baseURL 是 ``/api`` ⇒ 实际路径
    # ``/api/hr/employee-shop-assignments/batch``），这里**不要再加** prefix。
    app.include_router(router)

    async def _override_db():
        yield assignment_session

    app.dependency_overrides[get_async_db] = _override_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(user_id=1)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/hr/employee-shop-assignments/batch",
            json={
                "year_month": YEAR_MONTH,
                "mode": "create",
                "items": [
                    {
                        "employee_code": "EMP001",
                        "platform_code": "shopee",
                        "shop_id": "SHOP-A",
                        "commission_ratio": 0.15,
                    },
                    {
                        "employee_code": "EMP404",
                        "platform_code": "shopee",
                        "shop_id": "SHOP-B",
                        "commission_ratio": 0.05,
                    },
                ],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["summary"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert len(data["succeeded"]) == 1
    assert data["succeeded"][0]["employee_code"] == "EMP001"
    assert data["succeeded"][0]["id"] is not None
    assert len(data["failed"]) == 1
    assert "员工不存在" in data["failed"][0]["reason"]
    assert data["failed"][0]["target"]
