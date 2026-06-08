import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import backend.domains.business.routers.performance_management as performance_module
from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from modules.core.db import PerformanceScore


class _Result:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        if self._scalar_value is not None:
            return self._scalar_value
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _EmptyDb:
    async def execute(self, *_args, **_kwargs):
        return _Result(rows=[], scalar_value=0)


class _ConfigWriteDb:
    def __init__(self):
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    def add(self, obj):
        now = datetime.now(timezone.utc)
        obj.id = getattr(obj, "id", None) or 1
        obj.created_at = getattr(obj, "created_at", None) or now
        obj.updated_at = getattr(obj, "updated_at", None) or now
        self.added.append(obj)

    async def refresh(self, obj):
        now = datetime.now(timezone.utc)
        obj.id = getattr(obj, "id", None) or 1
        obj.created_at = getattr(obj, "created_at", None) or now
        obj.updated_at = getattr(obj, "updated_at", None) or now


def _user(role_code, permissions=(), *, username="user", is_superuser=False):
    return SimpleNamespace(
        user_id=1,
        username=username,
        is_superuser=is_superuser,
        roles=[
            SimpleNamespace(
                role_code=role_code,
                role_name=role_code,
                permissions=list(permissions),
            )
        ],
    )


def _app_with_overrides(db, user=None):
    app = FastAPI()
    app.include_router(performance_module.router, prefix="/api")

    async def _override_db():
        yield db

    app.dependency_overrides[get_async_db] = _override_db
    app.dependency_overrides[performance_module.get_async_db] = _override_db

    if user is not None:
        async def _override_user():
            return user

        app.dependency_overrides[get_current_user] = _override_user

    return app


@pytest.mark.asyncio
async def test_performance_read_endpoints_require_login_and_read_permission():
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb())),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/performance/config")
    assert response.status_code == 401

    no_read_user = _user("investor", permissions=["business-overview"])
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), no_read_user)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/performance/config")
    assert response.status_code == 403

    read_user = _user("manager", permissions=["performance:read"])
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), read_user)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/performance/config")
        assert response.status_code == 200
        response = await client.get("/api/performance/scores", params={"period": "2025-01"})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_performance_write_endpoints_require_admin_and_record_actor():
    manager = _user("manager", permissions=["performance:read"])
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_ConfigWriteDb(), manager)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/performance/config",
            json={"effective_from": "2025-01-01"},
        )
    assert response.status_code == 403

    db = _ConfigWriteDb()
    admin = _user("admin", permissions=["*"], username="alice", is_superuser=True)
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(db, admin)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/performance/config",
            json={"effective_from": "2025-01-01"},
        )
    assert response.status_code == 200
    assert db.added[0].created_by == "alice"

    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), manager)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/performance/scores/calculate",
            params={"period": "2025-01"},
        )
    assert response.status_code == 403


def test_active_config_query_has_stable_tiebreakers():
    class _CaptureDb:
        def __init__(self):
            self.first_stmt = None

        async def execute(self, stmt, *_args, **_kwargs):
            if self.first_stmt is None:
                self.first_stmt = stmt
            return _Result(rows=[], scalar_value=None)

    db = _CaptureDb()

    asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    order_by = [str(clause) for clause in db.first_stmt._order_by_clauses]
    assert any("effective_from" in clause for clause in order_by)
    assert any("updated_at" in clause for clause in order_by)
    assert any("id" in clause for clause in order_by)


def _json_body(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class _CalcDb:
    def __init__(self, config):
        self.config = config
        self.added = []
        self.execute_calls = 0
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, *_args, **_kwargs):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _Result(scalar_value=self.config)
        return _Result(rows=[], scalar_value=None)

    def add(self, obj):
        self.added.append(obj)


def _patch_successful_shop_recalc(monkeypatch, *, payroll_raises=False):
    async def _fake_target(_db, year_month, target_type, scope_type=None):
        if target_type == "operation":
            return SimpleNamespace(
                metric_direction="manual_score",
                target_value=None,
                achieved_value=None,
                max_score=20,
                manual_score_enabled=True,
                manual_score_value=20,
            )
        return None

    async def _fake_source_rows(_db, _period):
        return {
            "shopee|shop-1": {
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "target": 1000.0,
                "achieved": 1000.0,
                "target_profit_amount": 100.0,
                "achieved_profit_amount": 100.0,
                "key_product_target": 1_000_000.0,
                "key_product_achieved": 1_000_000.0,
            }
        }

    class _FakeIncomeService:
        def __init__(self, db, metabase_service=None):
            self.db = db
            self.metabase_service = metabase_service

        async def calculate_month(self, year_month, **kwargs):
            return {
                "year_month": year_month,
                "employee_count": 1,
                "commission_upserts": 1,
                "performance_upserts": 1,
            }

    class _FakePayrollService:
        def __init__(self, db):
            self.db = db

        async def generate_month(self, year_month):
            if payroll_raises:
                raise RuntimeError("payroll failed")
            return {
                "year_month": year_month,
                "payroll_upserts": 1,
                "locked_conflicts": 0,
                "locked_conflict_details": [],
            }

    monkeypatch.setattr(performance_module, "_load_effective_target_for_month", _fake_target)
    monkeypatch.setattr(performance_module, "load_shop_monthly_target_achievement", _fake_source_rows)
    monkeypatch.setattr(performance_module, "load_shop_monthly_metrics", AsyncMock(return_value={}))
    monkeypatch.setattr(performance_module, "_load_valid_performance_shop_keys", AsyncMock(return_value=None))
    monkeypatch.setattr(
        performance_module,
        "_load_shop_monthly_operating_days",
        AsyncMock(return_value={"shopee|shop-1": 31}),
    )
    monkeypatch.setattr(performance_module, "_load_prior_red_streak_by_shop", AsyncMock(return_value={}))
    monkeypatch.setattr(performance_module, "_sync_performance_alerts", AsyncMock(return_value=None))
    monkeypatch.setattr(performance_module, "HRIncomeCalculationService", _FakeIncomeService)
    monkeypatch.setattr(performance_module, "PayrollGenerationService", _FakePayrollService)
    monkeypatch.setattr(performance_module, "sync_performance_confirmation_task", AsyncMock(return_value=None))
    monkeypatch.setattr(performance_module, "invalidate_performance_related_caches", AsyncMock(return_value=None))


def _config():
    return SimpleNamespace(
        id=1,
        sales_max_score=30,
        profit_max_score=25,
        key_product_max_score=999,
        operation_max_score=20,
    )


def test_current_shop_formula_ignores_legacy_key_product_fields(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch)
    db = _CalcDb(_config())

    resp = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    assert _json_body(resp)["success"] is True
    created = next(item for item in db.added if isinstance(item, PerformanceScore))
    assert created.sales_score == 30
    assert created.profit_score == 25
    assert created.operation_score == 20
    assert created.key_product_score == 0
    assert created.total_score == 75
    assert created.score_details["key_product"]["status"] == "not_in_scope"
    assert "key_product" not in created.score_details["summary"]["ready_dimensions"]


def test_recalculation_commits_once_after_income_and_payroll(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch)
    db = _CalcDb(_config())

    resp = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    assert _json_body(resp)["success"] is True
    assert db.flush.await_count == 1
    assert db.commit.await_count == 1
    assert db.rollback.await_count == 0


def test_recalculation_rolls_back_when_payroll_generation_fails(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch, payroll_raises=True)
    db = _CalcDb(_config())

    resp = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    assert resp.status_code == 500
    assert db.commit.await_count == 0
    assert db.rollback.await_count == 1
