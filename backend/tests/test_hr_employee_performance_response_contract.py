"""员工绩效列表接口的响应契约：绩效待补（NULL）时不能 500。

背景
----
``c_class.employee_performance.performance_score`` 是**可空**列，而且现在的
计算口径是「算不出来就写 NULL + 明确状态」
（``calculation_status`` = ``pending_store_performance`` / ``pending_personal_input``），
**不再写 0 / 1 这种看起来像"算出来是 0 分"的占位值**。

旧契约把 ``performance_score`` 声明成必填 ``float``，于是只要有员工当月绩效
待补，整个列表接口就抛 Pydantic 校验错误 → HTTP 500，
**一个人的待补会把所有人的绩效页面一起打挂**。

这几条测试锁住：

1. 绩效分为 NULL 时能正常序列化（不再 500）；
2. 状态字段（``calculation_status`` / ``performance_source_type``）透出，
   前端才能区分"算出来是 0 分"和"还没算出来"；
3. 有分数的老行行为不变。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.schemas.hr import EmployeePerformanceResponse


def _row(**overrides):
    payload = {
        "id": 13,
        "employee_code": "EMP260001",
        "year_month": "2026-03",
        "actual_sales": Decimal("49460.01"),
        "achievement_rate": 0.20584355627101572,
        "performance_score": None,
        "calculation_status": "pending_store_performance",
        "performance_source_type": "pending",
        "calculated_at": datetime(2026, 11, 5, 12, 26, 24, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_pending_performance_score_serializes_as_null():
    response = EmployeePerformanceResponse.model_validate(_row())

    assert response.performance_score is None
    assert response.calculation_status == "pending_store_performance"
    assert response.performance_source_type == "pending"
    assert response.actual_sales == Decimal("49460.01")


def test_scored_performance_row_keeps_its_score():
    response = EmployeePerformanceResponse.model_validate(
        _row(
            year_month="2026-07",
            performance_score=75.56334846905537,
            calculation_status="complete",
            performance_source_type="controlled_targets_v1",
        )
    )

    assert response.performance_score == 75.56334846905537
    assert response.calculation_status == "complete"


def test_historical_placeholder_row_is_marked_as_historical():
    """老版本写的 0 / 1 占位行：分数照旧透出，但状态明确写成 historical。"""
    response = EmployeePerformanceResponse.model_validate(
        _row(
            performance_score=0.0,
            calculation_status="historical_unknown",
            performance_source_type="historical",
        )
    )

    assert response.performance_score == 0.0
    assert response.calculation_status == "historical_unknown"
    assert response.performance_source_type == "historical"


def test_response_model_allows_null_score():
    """契约层明确允许空绩效分（防止有人把它改回必填）。"""
    fields = EmployeePerformanceResponse.model_fields

    assert fields["performance_score"].annotation is not None
    assert not fields["performance_score"].is_required()
