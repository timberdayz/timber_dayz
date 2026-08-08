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

    def scalar_one(self):
        return self._scalar_value

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

    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb())),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/performance/period-status",
            params={"period": "2025-01"},
        )
    assert response.status_code == 401

    no_read_user = _user("investor", permissions=["business-overview"])
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), no_read_user)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/performance/config")
    assert response.status_code == 403

    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), no_read_user)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/performance/period-status",
            params={"period": "2025-01"},
        )
    assert response.status_code == 403

    read_user = _user("manager", permissions=["performance:read"])
    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), read_user)),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/performance/config")
        assert response.status_code == 200
        response = await client.get(
            "/api/performance/period-status",
            params={"period": "2025-01"},
        )
        assert response.status_code == 200
        response = await client.get("/api/performance/scores", params={"period": "2025-01"})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_performance_period_status_returns_locked_summary(monkeypatch):
    class _StatusService:
        def __init__(self, _db):
            pass

        async def get_month_lock_status(self, *, year_month):
            assert year_month == "2026-07"
            return {
                "period": year_month,
                "is_locked": True,
                "can_recalculate": False,
                "locked_record_count": 3,
                "locked_statuses": ["paid"],
                "reason": "payroll is paid",
            }

    monkeypatch.setattr(performance_module, "PayrollPeriodLockService", _StatusService)
    user = _user("manager", permissions=["performance:read"])

    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), user)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/performance/period-status",
            params={"period": "2026-07"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "period": "2026-07",
        "is_locked": True,
        "can_recalculate": False,
        "locked_record_count": 3,
        "locked_statuses": ["paid"],
        "reason": "payroll is paid",
    }


@pytest.mark.asyncio
async def test_performance_period_status_rejects_invalid_month_format():
    user = _user("manager", permissions=["performance:read"])

    async with AsyncClient(
        transport=ASGITransport(app=_app_with_overrides(_EmptyDb(), user)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/performance/period-status",
            params={"period": "July-2026"},
        )

    assert response.status_code == 422


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
            if self.first_stmt is None and "EXISTS" not in str(stmt):
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
    assert db.first_stmt._limit_clause is not None


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

    async def execute(self, statement, *_args, **_kwargs):
        self.execute_calls += 1
        if "EXISTS" in str(statement):
            return _Result(scalar_value=False)
        if "performance_config" in str(statement):
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
                "target_profit_basis_amount": 100.0,
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
    monkeypatch.setattr(
        performance_module,
        "_load_profit_basis_for_performance",
        AsyncMock(
            return_value={
                "shopee|shop-1": {
                    "profit_basis_amount": 100.0,
                    "basis_version": "A_ONLY_V1",
                    "calculation_mode": "formal",
                    "source": "finance.shop_profit_basis",
                }
            }
        ),
    )
    monkeypatch.setattr(performance_module, "_load_valid_performance_shop_keys", AsyncMock(return_value=None))
    monkeypatch.setattr(
        performance_module,
        "_load_shop_monthly_operating_days",
        AsyncMock(return_value={"shopee|shop-1": 31}),
    )
    monkeypatch.setattr(performance_module, "_load_prior_red_streak_by_shop", AsyncMock(return_value={}))
    monkeypatch.setattr(performance_module, "_sync_performance_alerts", AsyncMock(return_value=None))
    monkeypatch.setattr(
        performance_module,
        "_verify_persisted_shop_performance_keys",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(performance_module, "HRIncomeCalculationService", _FakeIncomeService)
    monkeypatch.setattr(performance_module, "PayrollGenerationService", _FakePayrollService)
    monkeypatch.setattr(performance_module, "sync_performance_confirmation_task", AsyncMock(return_value=None))
    monkeypatch.setattr(performance_module, "invalidate_performance_related_caches", AsyncMock(return_value=None))


def _config():
    return SimpleNamespace(
        id=1,
        sales_max_score=40,
        profit_max_score=40,
        key_product_max_score=999,
        operation_max_score=20,
    )


def test_shop_operation_breakdown_overrides_global_manual_score():
    operation_target = SimpleNamespace(
        metric_direction="manual_score",
        target_value=20.0,
        achieved_value=None,
        max_score=20.0,
        manual_score_enabled=True,
        manual_score_value=20.0,
    )
    shop_breakdown = SimpleNamespace(
        target_value=None,
        achieved_value=None,
        manual_score_value=7.25,
    )

    score, details = performance_module._calculate_operation_metric_score_for_shop(
        operation_target,
        shop_breakdown,
    )

    assert score == 7.25
    assert details["source"] == "target_management_shop_breakdown"
    assert details["calculation"] == "manual_score=7.25"


def test_recalculation_uses_shop_operation_breakdown(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch)
    monkeypatch.setattr(
        performance_module,
        "_load_operation_target_breakdown_by_shop",
        AsyncMock(
            return_value={
                "shopee|shop-1": SimpleNamespace(
                    target_value=None,
                    achieved_value=None,
                    manual_score_value=7.25,
                )
            }
        ),
        raising=False,
    )
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
    assert created.operation_score == 7.25
    assert created.score_details["operation"]["source"] == "target_management_shop_breakdown"


def test_ranking_policy_writes_canonical_formal_state():
    formal = {
        "platform_code": "shopee",
        "shop_id": "formal",
        "total_score": 90.0,
        "operation_score": 10.0,
        "profit_score": 30.0,
        "sales_score": 50.0,
        "score_details": {"summary": {"calculation_status": "complete"}},
    }
    low_coverage = {
        "platform_code": "shopee",
        "shop_id": "observation",
        "total_score": 80.0,
        "operation_score": 10.0,
        "profit_score": 30.0,
        "sales_score": 40.0,
        "score_details": {"summary": {"calculation_status": "complete"}},
    }

    performance_module._apply_ranking_policy(
        [formal, low_coverage],
        {"shopee|formal": 31, "shopee|observation": 14},
    )

    assert formal["score_details"]["summary"] == {
        "calculation_status": "complete",
        "operating_days": 31,
        "ranking_pool": "official",
        "formal_ready": True,
        "data_coverage_warning": False,
    }
    assert low_coverage["score_details"]["summary"] == {
        "calculation_status": "complete",
        "operating_days": 14,
        "ranking_pool": "official",
        "formal_ready": True,
        "data_coverage_warning": True,
    }
    assert low_coverage["rank"] == 2
    assert low_coverage["performance_coefficient"] is not None


def test_recalculation_rolls_back_on_invalid_period_value_error():
    db = _CalcDb(_config())

    response = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2026-invalid",
            config_id=None,
            db=db,
        )
    )

    assert _json_body(response)["success"] is False
    db.rollback.assert_awaited_once()


def test_persisted_shop_performance_validation_rejects_missing_business_key():
    class _Db:
        async def execute(self, _stmt):
            return _Result(rows=[("shopee", "shop-1")])

    with pytest.raises(RuntimeError, match="business keys"):
        asyncio.run(
            performance_module._verify_persisted_shop_performance_keys(
                _Db(),
                period="2026-06",
                expected_keys={"shopee|shop-1", "shopee|shop-2"},
            )
        )


def test_public_performance_coefficient_is_hidden_for_observation_result():
    details = {
        "summary": {
            "calculation_status": "complete",
            "ranking_pool": "observation",
            "formal_ready": False,
        }
    }

    assert performance_module._public_total_score(80.0, details) == 80.0
    assert performance_module._public_rank(2, details) is None
    assert performance_module._public_coefficient(1.2, details) is None


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
    assert created.sales_score == 40
    assert created.profit_score == 40
    assert created.operation_score == 20
    assert created.key_product_score == 0
    assert created.total_score == 100
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


def test_partial_recalculation_does_not_write_income_or_payroll(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch)
    downstream_calls = []

    async def _partial_source_rows(_db, _period):
        return {
            "shopee|shop-1": {
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "target": 1000.0,
                "achieved": 1000.0,
                "target_profit_amount": 0.0,
                "achieved_profit_amount": 0.0,
            }
        }

    class _IncomeService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def calculate_month(self, *_args, **_kwargs):
            downstream_calls.append("income")
            return {}

    class _PayrollService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_month(self, *_args, **_kwargs):
            downstream_calls.append("payroll")
            return {}

    monkeypatch.setattr(performance_module, "load_shop_monthly_target_achievement", _partial_source_rows)
    monkeypatch.setattr(performance_module, "HRIncomeCalculationService", _IncomeService)
    monkeypatch.setattr(performance_module, "PayrollGenerationService", _PayrollService)
    db = _CalcDb(_config())

    response = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    assert _json_body(response)["success"] is True
    assert downstream_calls == []
    created = next(item for item in db.added if isinstance(item, PerformanceScore))
    assert created.performance_coefficient is None


def test_monthly_score_uses_shop_target_and_locked_profit_basis(monkeypatch):
    _patch_successful_shop_recalc(monkeypatch)
    shop_target = SimpleNamespace(id=11)
    monthly_shop = SimpleNamespace(
        target_id=11,
        breakdown_type="shop",
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=1000.0,
        achieved_amount=1000.0,
        target_profit_basis_amount=100.0,
    )
    daily_projection = SimpleNamespace(
        target_id=11,
        breakdown_type="shop_time",
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=1000.0,
        achieved_amount=1000.0,
        target_profit_basis_amount=100.0,
    )
    locked_basis = SimpleNamespace(
        period_month="2025-01",
        platform_code="shopee",
        shop_id="shop-1",
        basis_version="A_ONLY_V1",
        is_locked=True,
        profit_basis_amount=100.0,
    )

    class _BasisDb(_CalcDb):
        def __init__(self):
            super().__init__(_config())
            self.target_breakdown_statement = None

        async def execute(self, statement, *_args, **_kwargs):
            text = str(statement)
            if "performance_config" in text:
                return _Result(scalar_value=self.config)
            if "target_breakdown" in text:
                self.target_breakdown_statement = statement
                if "POSTCOMPILE" in text:
                    return _Result(rows=[monthly_shop, daily_projection])
                return _Result(rows=[monthly_shop])
            if "shop_profit_basis" in text:
                return _Result(rows=[locked_basis])
            if "sales_targets" in text:
                return _Result(rows=[shop_target])
            return _Result(rows=[], scalar_value=None)

    monkeypatch.setattr(
        performance_module,
        "_load_effective_target_for_month",
        AsyncMock(return_value=shop_target),
    )
    monkeypatch.setattr(
        performance_module,
        "load_shop_monthly_metrics",
        AsyncMock(return_value={"shopee|shop-1": {"monthly_sales": 1000.0, "monthly_profit": 500.0}}),
    )
    monkeypatch.setattr(
        performance_module,
        "_load_operation_target_breakdown_by_shop",
        AsyncMock(return_value={}),
    )
    db = _BasisDb()

    response = asyncio.run(
        performance_module.calculate_performance_scores(
            period="2025-01",
            config_id=None,
            db=db,
        )
    )

    assert _json_body(response)["success"] is True
    score = next(item for item in db.added if isinstance(item, PerformanceScore))
    assert score.sales_score == 40.0
    assert score.profit_score == 40.0
    assert score.score_details["profit"]["source"] == "finance.shop_profit_basis"
    assert "POSTCOMPILE" not in str(db.target_breakdown_statement)


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
