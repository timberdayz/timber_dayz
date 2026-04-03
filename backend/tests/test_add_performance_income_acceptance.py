"""
add-performance-and-personal-income 验收测试

覆盖点:
1) /performance/scores/calculate 无配置 -> 404 + PERF_CONFIG_NOT_FOUND
2) /performance/scores/calculate 未就绪 -> 503 + PERF_CALC_NOT_READY
3) /performance/scores/calculate 周期格式错误 -> 400
4) /hr/me/income 未关联员工 -> linked=False 且触发审计调用
"""

import json
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from starlette.requests import Request

from backend.routers.hr_employee import get_my_income
import backend.routers.performance_management as performance_management_module
from backend.routers.performance_management import calculate_performance_scores, list_performance_scores
from modules.core.db import PerformanceScore


def _json_body(resp) -> dict:
    """从 JSONResponse 读取 JSON 内容。"""
    return json.loads(resp.body.decode("utf-8"))


def test_calculate_returns_404_when_config_missing():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    resp = asyncio.run(
        calculate_performance_scores(period="2025-01", config_id=None, db=db)
    )

    assert resp.status_code == 404
    body = _json_body(resp)
    assert body["success"] is False
    assert body["data"]["error_code"] == "PERF_CONFIG_NOT_FOUND"


def test_calculate_returns_503_when_not_ready():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(id=1)
    db.execute.return_value = result

    resp = asyncio.run(
        calculate_performance_scores(period="2025-01", config_id=None, db=db)
    )

    assert resp.status_code == 503
    body = _json_body(resp)
    assert body["success"] is False
    assert body["data"]["error_code"] == "PERF_CALC_NOT_READY"


def test_calculate_returns_400_when_period_invalid():
    db = AsyncMock()

    resp = asyncio.run(
        calculate_performance_scores(period="2025/01", config_id=None, db=db)
    )

    assert resp.status_code == 400
    body = _json_body(resp)
    assert body["success"] is False


def test_calculate_triggers_income_recalculation_and_returns_both_counts(monkeypatch):
    class _ScalarOneResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _ScalarsResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    config = SimpleNamespace(
        id=1,
        sales_max_score=30,
        profit_max_score=25,
        key_product_max_score=25,
        operation_max_score=20,
    )

    execute_calls = {"n": 0}

    async def _execute(_stmt):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ScalarOneResult(config)
        if n == 2:
            return _ScalarsResult([])
        if n == 3:
            return _ScalarOneResult(None)
        if n == 4:
            return _ScalarsResult([])
        if n == 5:
            return _ScalarOneResult(None)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    async def _fake_source_rows(_db, _period):
        return {
            "shopee|shop-1": {
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "target": 1000.0,
                "achieved": 800.0,
            }
        }

    income_calls = {"count": 0}
    payroll_calls = {"count": 0}

    class _FakeIncomeService:
        def __init__(self, db, metabase_service=None):
            self.db = db
            self.metabase_service = metabase_service

        async def calculate_month(self, year_month):
            income_calls["count"] += 1
            assert year_month == "2025-01"
            return {
                "year_month": year_month,
                "employee_count": 2,
                "commission_upserts": 2,
                "performance_upserts": 2,
                "source": "test",
            }

    class _FakePayrollService:
        def __init__(self, db):
            self.db = db

        async def generate_month(self, year_month):
            payroll_calls["count"] += 1
            assert year_month == "2025-01"
            return {
                "year_month": year_month,
                "payroll_upserts": 2,
                "locked_conflicts": 1,
            }

    monkeypatch.setattr(
        performance_management_module,
        "load_shop_monthly_target_achievement",
        _fake_source_rows,
    )
    monkeypatch.setattr(
        performance_management_module,
        "HRIncomeCalculationService",
        _FakeIncomeService,
        raising=False,
    )
    monkeypatch.setattr(
        performance_management_module,
        "PayrollGenerationService",
        _FakePayrollService,
        raising=False,
    )

    resp = asyncio.run(
        performance_management_module.calculate_performance_scores(
            period="2025-01", config_id=None, db=db
        )
    )

    body = _json_body(resp)
    assert body["success"] is True
    assert income_calls["count"] == 1
    assert payroll_calls["count"] == 1
    assert db.commit.await_count == 1
    assert body["data"]["shop_performance_upserts"] == 1
    assert body["data"]["commission_upserts"] == 2
    assert body["data"]["employee_performance_upserts"] == 2
    assert body["data"]["payroll_upserts"] == 2
    assert body["data"]["payroll_locked_conflicts"] == 1
    perf_score_rows = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and isinstance(call.args[0], PerformanceScore)
    ]
    assert len(perf_score_rows) == 1
    created = perf_score_rows[0]
    assert created.sales_score == 24.0
    assert created.profit_score == 0.0
    assert created.key_product_score == 0.0
    assert created.operation_score == 0.0
    assert created.total_score == 24.0
    assert created.score_details["sales"]["status"] == "calculated"
    assert created.score_details["profit"]["status"] == "pending_design"
    assert created.score_details["key_product"]["status"] == "pending_design"
    assert created.score_details["operation"]["status"] == "pending_design"


def test_list_scores_shop_hides_pending_dimensions_from_partial_results():
    class _ShopRows:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _PerfRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    db = AsyncMock()
    shop = SimpleNamespace(
        platform="Shopee",
        store_name="Shop 1",
        shop_id="shop-1",
        account_id=None,
        id=1,
        enabled=True,
    )
    score = SimpleNamespace(
        platform_code="shopee",
        shop_id="shop-1",
        period="2025-01",
        sales_score=24.0,
        profit_score=0.0,
        key_product_score=0.0,
        operation_score=0.0,
        total_score=24.0,
        rank=1,
        performance_coefficient=1.0,
        score_details={
            "sales": {"status": "calculated", "target": 1000.0, "achieved": 800.0, "rate": 80.0},
            "profit": {"status": "pending_design", "achieved": 200.0},
            "key_product": {"status": "pending_design"},
            "operation": {"status": "pending_design"},
            "summary": {"status": "partial"},
        },
    )

    execute_calls = {"n": 0}

    async def _execute(_stmt):
        execute_calls["n"] += 1
        if execute_calls["n"] == 1:
            return _ShopRows([shop])
        if execute_calls["n"] == 2:
            return _PerfRows([(score,)])
        raise AssertionError(f"unexpected execute call #{execute_calls['n']}")

    db.execute = AsyncMock(side_effect=_execute)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/performance/scores",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )

    resp = asyncio.run(
        list_performance_scores(
            request=request,
            period="2025-01",
            platform_code=None,
            shop_id=None,
            group_by="shop",
            page=1,
            page_size=20,
            db=db,
        )
    )

    body = _json_body(resp)
    row = body["data"][0]
    assert row["sales_score"] == 24.0
    assert row["profit_score"] is None
    assert row["key_product_score"] is None
    assert row["operation_score"] is None
    assert row["total_score"] is None
    assert row["rank"] is None
    assert row["performance_coefficient"] is None


def test_calculate_profit_score_from_profit_target_and_actual(monkeypatch):
    class _ScalarOneResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _ScalarsResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    config = SimpleNamespace(
        id=1,
        sales_max_score=30,
        profit_max_score=25,
        key_product_max_score=25,
        operation_max_score=20,
    )
    target_breakdown_row = SimpleNamespace(
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=1000.0,
        achieved_amount=800.0,
        target_profit_amount=500.0,
        achieved_profit_amount=200.0,
    )

    execute_calls = {"n": 0}

    async def _execute(_stmt):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ScalarOneResult(config)
        if n == 2:
            return _ScalarsResult([target_breakdown_row])
        if n == 3:
            return _ScalarOneResult(None)
        if n == 4:
            return _ScalarsResult([])
        if n == 5:
            return _ScalarOneResult(None)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    async def _fake_metrics(_db, _period):
        return {
            "shopee|shop-1": {
                "monthly_sales": 800.0,
                "monthly_profit": 200.0,
                "achievement_rate": 80.0,
            }
        }

    class _FakeIncomeService:
        def __init__(self, db, metabase_service=None):
            self.db = db

        async def calculate_month(self, year_month):
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
            }

    monkeypatch.setattr(performance_management_module, "load_shop_monthly_metrics", _fake_metrics)
    monkeypatch.setattr(performance_management_module, "HRIncomeCalculationService", _FakeIncomeService, raising=False)

    resp = asyncio.run(
        performance_management_module.calculate_performance_scores(
            period="2025-01", config_id=None, db=db
        )
    )

    body = _json_body(resp)
    assert body["success"] is True
    perf_score_rows = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and isinstance(call.args[0], PerformanceScore)
    ]
    assert len(perf_score_rows) == 1
    created = perf_score_rows[0]
    assert created.sales_score == 24.0
    assert created.profit_score == 10.0
    assert created.total_score == 34.0
    assert created.score_details["profit"]["status"] == "calculated"
    assert created.score_details["profit"]["target"] == 500.0
    assert created.score_details["profit"]["achieved"] == 200.0
    assert created.score_details["profit"]["rate"] == 40.0


def test_calculate_operation_score_from_operation_target_rule(monkeypatch):
    class _ScalarOneResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _ScalarsResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows
        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    config = SimpleNamespace(
        id=1,
        sales_max_score=30,
        profit_max_score=25,
        key_product_max_score=25,
        operation_max_score=20,
    )
    target_breakdown_row = SimpleNamespace(
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=1000.0,
        achieved_amount=800.0,
        target_profit_amount=500.0,
        achieved_profit_amount=200.0,
    )
    operation_target = SimpleNamespace(
        id=2,
        target_type="operation",
        target_name="2025-01 客诉目标",
        period_start=SimpleNamespace(),
        period_end=SimpleNamespace(),
        metric_code="complaint_count",
        metric_name="客诉",
        metric_direction="lower_better",
        target_value=3.0,
        achieved_value=6.0,
        max_score=20.0,
        penalty_enabled=True,
        penalty_threshold=5.0,
        penalty_per_unit=2.0,
        penalty_max=10.0,
        manual_score_enabled=False,
        manual_score_value=None,
    )

    execute_calls = {"n": 0}

    async def _execute(_stmt):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ScalarOneResult(config)
        if n == 2:
            return _ScalarsResult([target_breakdown_row])
        if n == 3:
            return _ScalarsResult([operation_target])
        if n == 4:
            return _ScalarsResult([])
        if n == 5:
            return _ScalarOneResult(None)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    async def _fake_metrics(_db, _period):
        return {
            "shopee|shop-1": {
                "monthly_sales": 800.0,
                "monthly_profit": 200.0,
                "achievement_rate": 80.0,
            }
        }

    class _FakeIncomeService:
        def __init__(self, db, metabase_service=None):
            self.db = db

        async def calculate_month(self, year_month):
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
            }

    monkeypatch.setattr(performance_management_module, "load_shop_monthly_metrics", _fake_metrics)
    monkeypatch.setattr(performance_management_module, "HRIncomeCalculationService", _FakeIncomeService, raising=False)

    resp = asyncio.run(
        performance_management_module.calculate_performance_scores(
            period="2025-01", config_id=None, db=db
        )
    )

    body = _json_body(resp)
    assert body["success"] is True
    perf_score_rows = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and isinstance(call.args[0], PerformanceScore)
    ]
    assert len(perf_score_rows) == 1
    created = perf_score_rows[0]
    assert created.operation_score == 8.0
    assert created.total_score == 42.0
    assert created.score_details["operation"]["status"] == "calculated"
    assert created.score_details["operation"]["target"] == 3.0
    assert created.score_details["operation"]["achieved"] == 6.0


def test_calculate_key_product_score_from_product_target_and_sku_metrics(monkeypatch):
    class _ScalarOneResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _ScalarsResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    config = SimpleNamespace(
        id=1,
        sales_max_score=30,
        profit_max_score=25,
        key_product_max_score=25,
        operation_max_score=20,
    )
    target_breakdown_row = SimpleNamespace(
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=1000.0,
        achieved_amount=800.0,
        target_profit_amount=500.0,
        achieved_profit_amount=200.0,
    )
    product_target = SimpleNamespace(
        id=3,
        target_type="product",
        platform_sku="sku-1",
        product_id=None,
        company_sku=None,
    )
    product_breakdown = SimpleNamespace(
        target_id=3,
        breakdown_type="shop",
        platform_code="shopee",
        shop_id="shop-1",
        target_amount=300.0,
    )

    execute_calls = {"n": 0}

    async def _execute(_stmt):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ScalarOneResult(config)
        if n == 2:
            return _ScalarsResult([target_breakdown_row])
        if n == 3:
            return _ScalarOneResult(None)
        if n == 4:
            return _ScalarsResult([product_target])
        if n == 5:
            return _ScalarsResult([product_breakdown])
        if n == 6:
            return _ScalarOneResult(None)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    async def _fake_metrics(_db, _period):
        return {
            "shopee|shop-1": {
                "monthly_sales": 800.0,
                "monthly_profit": 200.0,
                "achievement_rate": 80.0,
            }
        }

    async def _fake_product_metrics(_db, _period):
        return {
            "shopee|shop-1|sku:sku-1": {
                "sales_amount": 150.0,
                "order_count": 20.0,
            }
        }

    class _FakeIncomeService:
        def __init__(self, db, metabase_service=None):
            self.db = db

        async def calculate_month(self, year_month):
            return {
                "year_month": year_month,
                "employee_count": 0,
                "commission_upserts": 0,
                "performance_upserts": 0,
            }

    monkeypatch.setattr(performance_management_module, "load_shop_monthly_metrics", _fake_metrics)
    monkeypatch.setattr(performance_management_module, "_load_shop_monthly_product_metrics", _fake_product_metrics)
    monkeypatch.setattr(performance_management_module, "HRIncomeCalculationService", _FakeIncomeService, raising=False)

    resp = asyncio.run(
        performance_management_module.calculate_performance_scores(
            period="2025-01", config_id=None, db=db
        )
    )

    body = _json_body(resp)
    assert body["success"] is True
    perf_score_rows = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and isinstance(call.args[0], PerformanceScore)
    ]
    assert len(perf_score_rows) == 1
    created = perf_score_rows[0]
    assert created.key_product_score == 12.5
    assert created.total_score == 46.5
    assert created.score_details["key_product"]["status"] == "calculated"
    assert created.score_details["key_product"]["target"] == 300.0
    assert created.score_details["key_product"]["achieved"] == 150.0
    assert created.score_details["key_product"]["rate"] == 50.0


def test_my_income_unlinked_returns_linked_false_and_audit_called(monkeypatch):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1001)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is False
    assert called["count"] == 1


def _deprecated_my_income_linked_fallback_to_cn_columns_when_orm_columns_missing(monkeypatch):
    class _ResultOne:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _RawMapResult:
        def __init__(self, value):
            self._value = value

        def mappings(self):
            return self

        def first(self):
            return self._value

    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP001")
    execute_calls = {"n": 0}

    async def _execute(_stmt, _params=None):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        # 查询 employee
        if n == 1:
            return _ResultOne(employee)
        # 查询 payroll_records
        if n == 2:
            return _ResultOne(None)
        # 查询 salary_structures
        if n == 3:
            return _ResultOne(None)
        # ORM 查询 employee_commissions 失败 -> 触发 fallback
        if n == 4:
            raise Exception("column employee_commissions.employee_code does not exist")
        # fallback employee_commissions(中文列)
        if n == 5:
            return _RawMapResult({"commission_amount": 123.45})
        # ORM 查询 employee_performance 失败 -> 触发 fallback
        if n == 6:
            raise Exception("column employee_performance.employee_code does not exist")
        # fallback employee_performance(中文列)
        if n == 7:
            return _RawMapResult({"performance_score": 88.0, "achievement_rate": 0.76})
        return _ResultOne(None)

    db.execute = AsyncMock(side_effect=_execute)
    db.rollback = AsyncMock()

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1002)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is True
    assert float(resp.commission_amount) == 123.45
    assert float(resp.performance_score) == 88.0
    assert abs(float(resp.achievement_rate) - 0.76) < 1e-9
    assert db.rollback.await_count >= 2
    assert called["count"] == 1


def test_my_income_linked_uses_payroll_net_salary_only_and_skips_fallback(monkeypatch):
    class _ResultOne:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP009")
    payroll = SimpleNamespace(
        employee_code="EMP009",
        year_month="2025-01",
        base_salary=1000.0,
        commission=300.0,
        net_salary=1888.0,
        performance_salary=200.0,
        allowances=100.0,
        total_deductions=12.0,
        gross_salary=1900.0,
        status="draft",
    )
    execute_calls = {"n": 0}

    async def _execute(_stmt, _params=None):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ResultOne(employee)
        if n == 2:
            return _ResultOne(payroll)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1003)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is True
    assert float(resp.total_income) == 1888.0
    assert resp.breakdown == {
        "payroll": {
            "base_salary": 1000.0,
            "commission": 300.0,
            "net_salary": 1888.0,
        }
    }
    assert called["count"] == 1


def test_my_income_linked_without_payroll_returns_empty_income_state(monkeypatch):
    class _ResultOne:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    db = AsyncMock()
    employee = SimpleNamespace(employee_code="EMP010")
    execute_calls = {"n": 0}

    async def _execute(_stmt, _params=None):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ResultOne(employee)
        if n == 2:
            return _ResultOne(None)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)

    called = {"count": 0}

    async def _fake_log(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("backend.routers.hr_employee._log_me_income_access", _fake_log)

    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "method": "GET",
            "path": "/api/hr/me/income",
        }
    )
    user = SimpleNamespace(user_id=1004)

    resp = asyncio.run(
        get_my_income(request=request, year_month="2025-01", current_user=user, db=db)
    )

    assert resp.linked is True
    assert resp.total_income is None
    assert resp.breakdown == {}
    assert called["count"] == 1
