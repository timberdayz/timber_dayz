"""提成试算预览接口的守护（批次 5 · 页面收敛）。

背景（ADR-2026-11-21）：提成口径已归一为
``提成 = max(可分配利润, 0) × 归属提成比``（**零系数**），
真源在 :mod:`backend.services.commission_caliber`。

前端以前自己乘一遍「利润基数 × 可分配率 × 提成比 × 系数」来显示
「改了还没保存」的试算值 —— 那是**第二套口径**，页面上的钱会和工资单对不上。
现在前端只把待保存的**输入**交给本接口，由后端按唯一口径算钱。

本守护验证：

1. 试算金额与唯一真源一致（且**不乘任何系数**）；
2. 亏损（负利润基数）按 0 处理；
3. 接口存在、要求管理员权限、只读不写库。
"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.hr_income_calculation_service import HRIncomeCalculationService


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _make_db(basis_rows=None, config_rows=None):
    """构造一个只会返回利润基数 / 可分配率配置的假 DB。"""

    db = AsyncMock()

    async def _execute(statement, *args, **kwargs):
        text = str(statement)
        if "shop_profit_basis" in text:
            return _ScalarResult(basis_rows or [])
        if "shop_commission_config" in text:
            return _ScalarResult(config_rows or [])
        return _ScalarResult([])

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _basis_row(
    platform_code="shopee",
    shop_id="S1",
    profit_basis_amount=480.0,
    cost_status="complete",
    basis_version="SETTLEMENT_BASIS_V1",
):
    return SimpleNamespace(
        platform_code=platform_code,
        shop_id=shop_id,
        profit_basis_amount=profit_basis_amount,
        cost_status=cost_status,
        basis_version=basis_version,
    )


def _config_row(platform_code="shopee", shop_id="S1", rate=0.25):
    return SimpleNamespace(
        year_month="2026-10",
        platform_code=platform_code,
        shop_id=shop_id,
        allocatable_profit_rate=rate,
    )


def _override(
    employee_code="E001",
    platform_code="shopee",
    shop_id="S1",
    commission_ratio=0.5,
    allocatable_profit_rate=0.25,
):
    return {
        "employee_code": employee_code,
        "platform_code": platform_code,
        "shop_id": shop_id,
        "commission_ratio": commission_ratio,
        "allocatable_profit_rate": allocatable_profit_rate,
    }


def test_estimate_matches_single_source_caliber():
    """试算金额 = 可分配利润 × 归属提成比（零系数）。"""
    db = _make_db(
        basis_rows=[_basis_row(profit_basis_amount=480.0)],
        config_rows=[_config_row(rate=0.25)],
    )
    service = HRIncomeCalculationService(db=db)

    result = asyncio.run(service.build_commission_estimate("2026-10", [_override()]))

    assert result["year_month"] == "2026-10"
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    # 480 × 0.25 = 120；120 × 0.5 = 60
    assert row["profit_basis_amount"] == 480.0
    assert row["allocatable_profit_amount"] == 120.0
    assert row["estimated_commission"] == 60.0


def test_estimate_does_not_multiply_any_coefficient():
    """提成零系数：提成比翻倍，金额必须恰好翻倍（无系数介入）。"""
    db = _make_db(
        basis_rows=[_basis_row(profit_basis_amount=1000.0)],
        config_rows=[_config_row(rate=0.25)],
    )
    service = HRIncomeCalculationService(db=db)

    rows = asyncio.run(
        service.build_commission_estimate(
            "2026-10",
            [
                _override(commission_ratio=0.2, allocatable_profit_rate=0.25),
                _override(commission_ratio=0.4, allocatable_profit_rate=0.25),
            ],
        )
    )["rows"]

    # 1000 × 0.25 = 250 可分配利润；提成比翻倍 ⇒ 金额恰好翻倍
    assert rows[0]["allocatable_profit_amount"] == 250.0
    assert rows[0]["estimated_commission"] == 50.0
    assert rows[1]["estimated_commission"] == 100.0


def test_estimate_floors_negative_profit_basis_at_zero():
    """亏损店不产生负提成。"""
    db = _make_db(
        basis_rows=[_basis_row(profit_basis_amount=-480.0)],
        config_rows=[_config_row(rate=0.25)],
    )
    service = HRIncomeCalculationService(db=db)

    row = asyncio.run(service.build_commission_estimate("2026-10", [_override()]))[
        "rows"
    ][0]

    assert row["allocatable_profit_amount"] == 0.0
    assert row["estimated_commission"] == 0.0
    assert row["commission_zero_reason"]


def test_estimate_reports_missing_basis_instead_of_silently_zero():
    """没有利润基数时必须给出业务原因，不能静默显示 0。"""
    db = _make_db(basis_rows=[], config_rows=[_config_row(rate=0.25)])
    service = HRIncomeCalculationService(db=db)

    row = asyncio.run(service.build_commission_estimate("2026-10", [_override()]))[
        "rows"
    ][0]

    assert row["cost_status"] == "missing_labor_allocation"
    assert row["commission_zero_reason"]


def test_estimate_returns_empty_rows_when_nothing_to_estimate():
    db = _make_db()
    service = HRIncomeCalculationService(db=db)

    result = asyncio.run(service.build_commission_estimate("2026-10", []))

    assert result == {"year_month": "2026-10", "rows": []}


def test_estimate_is_read_only():
    """试算只读：不得写库。"""
    source = inspect.getsource(HRIncomeCalculationService.build_commission_estimate)
    for forbidden in ("add(", "delete(", "flush(", "commit("):
        assert forbidden not in source, f"试算接口不允许写库：出现了 {forbidden}"


def test_estimate_endpoint_exists_and_requires_admin():
    """接口存在，且必须走管理员鉴权。"""
    from backend.domains.business.routers import hr_commission as module

    routes = {
        getattr(route, "path", ""): route
        for route in module.router.routes
        if getattr(route, "path", "").startswith("/api/hr/commissions")
    }
    path = "/api/hr/commissions/settlement-preview/estimate"
    assert path in routes, f"缺少试算接口：{path}"

    route = routes[path]
    assert "POST" in getattr(route, "methods", set())

    source = inspect.getsource(module.post_commission_settlement_estimate)
    assert "require_admin" in source
    # 只读：不得出现写库方法
    for forbidden in ("db.add", "db.delete", "db.commit", "db.flush"):
        assert forbidden not in source


def test_estimate_request_schema_rejects_invalid_ratio():
    """试算入参必须有界（比例 0-1）。"""
    from backend.schemas.hr import CommissionEstimateRequest

    with pytest.raises(Exception):
        CommissionEstimateRequest(
            year_month="2026-10",
            overrides=[
                {
                    "employee_code": "E001",
                    "platform_code": "shopee",
                    "shop_id": "S1",
                    "commission_ratio": 1.5,
                    "allocatable_profit_rate": 0.25,
                }
            ],
        )
