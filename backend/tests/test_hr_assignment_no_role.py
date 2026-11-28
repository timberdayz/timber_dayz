"""「员工店铺归属」的归属角色（supervisor/operator）退休守护。

系统里有两个都叫「角色」的东西，本次**只**退休第 2 个：

* ✅ **访问权限角色**（admin/manager/operator/finance，存在 ``core.dim_users.roles``）
  —— 一行不动；
* ❌ **归属角色**（``a_class.employee_shop_assignments.role``）—— 本批次彻底删除。

归属配置只回答「谁在这家店分多少提成」：一行 = 人 × 平台 × 店 × 月 × 提成比。
提成金额口径「可分配利润 × 归属提成比（零系数）」**不变**。

本文件守护三件事：

1. 归属的写入 / 读取 / 复制**不再有 role**，旧页面带 role 也不会报错；
2. 「每月成本录入任务」整条链路已删除（成本录入照常成功、不再派任务）；
3. 迁移 ``20261244`` **可升可降**。
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.hr import (
    CopyFromPrevMonthBody,
    EmployeeShopAssignmentCreate,
    EmployeeShopAssignmentResponse,
    EmployeeShopAssignmentUpdate,
)
from modules.core.db import (
    Base,
    DimPlatform,
    DimShop,
    Employee,
    EmployeeShopAssignment,
    PersonalPerformanceAssignmentSnapshot,
)

MIGRATION_PATH = Path(
    "current_migrations/versions/20261244_drop_employee_shop_assignment_role.py"
)

CURRENT_MONTH = "2026-11"
NEXT_MONTH = "2026-12"


# ---------------------------------------------------------------------------
# 契约层：schema 里没有 role，且旧页面带 role 也不报错
# ---------------------------------------------------------------------------


def test_assignment_schemas_no_longer_expose_role():
    """三个归属 schema 都不再有 role 字段。"""
    assert "role" not in EmployeeShopAssignmentCreate.model_fields
    assert "role" not in EmployeeShopAssignmentUpdate.model_fields
    assert "role" not in EmployeeShopAssignmentResponse.model_fields


def test_assignment_create_ignores_legacy_role_field():
    """兼容：旧页面仍会带 role ⇒ 被忽略，而不是报错。"""
    payload = EmployeeShopAssignmentCreate.model_validate(
        {
            "year_month": CURRENT_MONTH,
            "employee_code": "EMP260001",
            "platform_code": "shopee",
            "shop_id": "XHKJ11_SG",
            "commission_ratio": 0.05,
            "role": "supervisor",
        }
    )

    assert payload.commission_ratio == 0.05
    assert "role" not in payload.model_dump()
    assert not hasattr(payload, "role")


def test_assignment_update_ignores_legacy_role_field():
    payload = EmployeeShopAssignmentUpdate.model_validate(
        {"commission_ratio": 0.05, "role": "operator"}
    )

    assert payload.commission_ratio == 0.05
    assert "role" not in payload.model_dump()


def test_assignment_table_no_longer_has_role_column():
    """ORM 是 schema 的 SSOT：列没了，写入/读取就不可能再带上 role。"""
    assert "role" not in EmployeeShopAssignment.__table__.c
    assert "role_snapshot" not in PersonalPerformanceAssignmentSnapshot.__table__.c


# ---------------------------------------------------------------------------
# 功能层：写入 / 读取 / 复制都不再有 role
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def assignment_session(pg_database):
    """每个用例独占一个 database（写接口内部会 commit ⇒ 不能靠回滚隔离）。"""
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
                DimShop(platform_code="shopee", shop_id="XHKJ11_SG", shop_name="西虹店")
            )
            session.add(
                Employee(employee_code="EMP260001", name="泽伟", status="active")
            )
            await session.commit()
            yield session
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_read_assignment_carry_no_role(assignment_session):
    from backend.domains.business.routers.hr_commission import (
        create_employee_shop_assignment,
        list_employee_shop_assignments,
    )

    created = await create_employee_shop_assignment(
        body=EmployeeShopAssignmentCreate.model_validate(
            {
                "year_month": CURRENT_MONTH,
                "employee_code": "EMP260001",
                "platform_code": "shopee",
                "shop_id": "XHKJ11_SG",
                "commission_ratio": 0.15,
                "role": "supervisor",  # 旧页面仍会带 ⇒ 必须被忽略
            }
        ),
        db=assignment_session,
        _current_user=SimpleNamespace(user_id=1),
    )

    assert created["success"] is True
    payload = created["data"]
    assert "role" not in payload.model_dump()
    assert payload.commission_ratio == 0.15

    listed = await list_employee_shop_assignments(
        year_month=CURRENT_MONTH,
        employee_code=None,
        shop_id=None,
        platform_code=None,
        status=None,
        page=1,
        page_size=20,
        db=assignment_session,
    )
    items = listed["data"]["items"]
    assert len(items) == 1
    assert "role" not in items[0].model_dump()


@pytest.mark.asyncio
async def test_copy_from_prev_month_does_not_copy_role(assignment_session):
    from backend.domains.business.routers.hr_commission import (
        copy_employee_shop_assignments_from_prev_month,
        create_employee_shop_assignment,
    )

    await create_employee_shop_assignment(
        body=EmployeeShopAssignmentCreate.model_validate(
            {
                "year_month": CURRENT_MONTH,
                "employee_code": "EMP260001",
                "platform_code": "shopee",
                "shop_id": "XHKJ11_SG",
                "commission_ratio": 0.15,
                "role": "supervisor",
            }
        ),
        db=assignment_session,
        _current_user=SimpleNamespace(user_id=1),
    )

    copied = await copy_employee_shop_assignments_from_prev_month(
        body=CopyFromPrevMonthBody(year_month=NEXT_MONTH),
        db=assignment_session,
        current_user=SimpleNamespace(user_id=1),
    )

    assert copied["success"] is True
    assert copied["data"]["copied"] == 1

    rows = (
        (
            await assignment_session.execute(
                sa.select(EmployeeShopAssignment).where(
                    EmployeeShopAssignment.year_month == NEXT_MONTH
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].commission_ratio == 0.15


# ---------------------------------------------------------------------------
# 「每月成本录入任务」整条链路已删除
# ---------------------------------------------------------------------------


def test_task_policy_no_longer_has_monthly_cost_entry():
    from backend.services.employee_task_policy import (
        TASK_TYPE_POLICIES,
        get_task_type_policy,
    )

    assert "monthly_cost_entry" not in TASK_TYPE_POLICIES
    with pytest.raises(ValueError, match="Unknown task type"):
        get_task_type_policy("monthly_cost_entry")


def test_task_sources_no_longer_resolve_shop_supervisor():
    from backend.services import employee_task_sources

    assert not hasattr(employee_task_sources, "resolve_shop_supervisor_user_id")
    assert not hasattr(employee_task_sources, "sync_monthly_cost_entry_task")


def test_expense_router_no_longer_dispatches_cost_entry_task():
    from backend.domains.business.routers import expense_management as module

    assert not hasattr(module, "sync_monthly_cost_entry_task")


@pytest.mark.asyncio
async def test_expense_upsert_succeeds_without_dispatching_any_task(monkeypatch):
    """成本录入照常成功（200），并且**不再**派发协同任务。"""
    from backend.domains.business.routers import expense_management as module

    executed_sql: list[str] = []

    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _DB:
        async def execute(self, query, params=None):
            sql = str(query)
            executed_sql.append(sql)
            if "SELECT COALESCE(is_locked, false)" in sql:
                return _Result(None)
            if "SELECT deleted_at" in sql and "a_class.operating_costs" in sql:
                # 2026-11-28：普通保存前会探测同键**软删行**，命中才报 400
                # （复活只走 /restore）。本用例没有软删行 ⇒ 放行。
                return _Result(None)
            if "INSERT INTO a_class.operating_costs" in sql:
                return _Result(
                    SimpleNamespace(
                        id=1,
                        shop_id=params["shop_id"],
                        platform_code=params["platform_code"],
                        year_month=params["year_month"],
                        rent=params["rent"],
                        marketing_fee=params["marketing_fee"],
                        utilities=params["utilities"],
                        ai_token_cost=params["ai_token_cost"],
                        labor_cost=params["labor_cost"],
                        other_costs=params["other_costs"],
                        total_cost=params["total_cost"],
                        note=params["note"],
                        attachments=[],
                        locked=False,
                        created_at="2026-05-25T00:00:00Z",
                        updated_at="2026-05-25T00:00:00Z",
                    )
                )
            raise AssertionError(sql)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def _override_db():
        yield _DB()

    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id=1,
        username="tester",
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )
    app.dependency_overrides[get_async_db] = _override_db

    async def _allow_manual_labor_cost(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        "backend.services.labor_cost_policy_service.LaborCostPolicyService.is_manual_labor_cost_allowed",
        _allow_manual_labor_cost,
    )
    monkeypatch.setattr(
        module,
        "_resolve_shop_platform_code",
        lambda db, shop_id: __import__("asyncio").sleep(0, result="shopee"),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/expenses",
            json={
                "shop_id": "shop-1",
                "platform_code": "",
                "year_month": "2026-05",
                "rent": 1,
                "marketing_fee": 2,
                "utilities": 3,
                "ai_token_cost": 4,
                "labor_cost": 6,
                "other_costs": 5,
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    # 没有派发任何协同任务 ⇒ 不会有写 employee_tasks 的 SQL
    assert not any("employee_tasks" in sql for sql in executed_sql)


# ---------------------------------------------------------------------------
# 迁移契约：可升可降
# ---------------------------------------------------------------------------


def _load_migration_module():
    """按路径加载迁移模块（文件名以数字开头，不能用普通 import）。"""
    spec = importlib.util.spec_from_file_location(
        "migration_20261244_drop_employee_shop_assignment_role", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_exists_and_chains_from_previous_head():
    assert MIGRATION_PATH.exists(), "缺 20261244 归属角色退休迁移"

    module = _load_migration_module()
    assert (
        module.revision == "current_schema_20261244_drop_employee_shop_assignment_role"
    )
    assert module.down_revision == "current_schema_20261243_drop_legacy_profit_basis"
    # ⚠️ version_num 列是 String(64) ⇒ revision 超长会在写版本号时炸
    assert len(module.revision) <= 64


def test_migration_source_documents_background_and_reversibility():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "employee_shop_assignments" in source
    assert "role_snapshot" in source
    assert "sa.inspect(op.get_bind())" in source
    # 升级与降级都要有
    assert "def upgrade()" in source
    assert "def downgrade()" in source


@pytest.mark.asyncio
async def test_migration_upgrade_drops_role_and_downgrade_restores_it(pg_database):
    """真跑一遍：升级删列、降级加回列（可升可降）。"""
    async with pg_database() as pg:
        sync_url = pg.get_connection_url()
        engine = sa.create_engine(sync_url)
        with engine.begin() as conn:
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS "a_class"'))
            conn.execute(
                text(
                    """
                    CREATE TABLE a_class.employee_shop_assignments (
                        id BIGSERIAL PRIMARY KEY,
                        year_month VARCHAR(7) NOT NULL,
                        employee_code VARCHAR(64) NOT NULL,
                        role VARCHAR(32)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE a_class.personal_performance_assignment_snapshots (
                        id BIGSERIAL PRIMARY KEY,
                        role_snapshot VARCHAR(32)
                    )
                    """
                )
            )

            module = _load_migration_module()
            module.op = Operations(MigrationContext.configure(conn))

            module.upgrade()
            assert "role" not in _column_names(
                conn, "a_class", "employee_shop_assignments"
            )
            assert "role_snapshot" not in _column_names(
                conn, "a_class", "personal_performance_assignment_snapshots"
            )

            module.downgrade()
            assert "role" in _column_names(conn, "a_class", "employee_shop_assignments")
            assert "role_snapshot" in _column_names(
                conn, "a_class", "personal_performance_assignment_snapshots"
            )
        engine.dispose()


def _column_names(conn, schema: str, table: str) -> set:
    inspector = sa.inspect(conn)
    if not inspector.has_table(table, schema=schema):
        return set()
    return {column["name"] for column in inspector.get_columns(table, schema=schema)}
