"""月度结算单：把一个月的结算事实聚成一页。

为什么要有这一页
----------------
以前要回答「这个月到底发了多少钱、卡在谁身上」，要在四五个页面之间来回跳：
绩效页看分数、归属页看提成、工资页看实发、日志页看报错。
而且各页各算各的，出现过「页面 1002.56 / 后端统计 1002.55 / 实发 979.46」。

这一页把**唯一事实源**原样摆出来：

* 店铺维度：绩效分、排名、结算系数、利润基数、可分配率、当月状态（亏损 / 不参与考核）
* 员工维度：绩效分、结算系数、绩效工资、提成、实发、工资单状态、当月状态
* 阻断项：谁卡住了、缺什么、下一步去哪补

**这里不做任何二次计算**：所有金额直接取已落库的结果，
系数取已落库的结算系数，状态取绩效模块写入的状态。
所以这一页看到的，就是工资单拿到的。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.commission_reason_service import commission_zero_reason
from backend.services.performance_readiness_service import PerformanceReadinessService
from modules.core.db import (
    Employee,
    EmployeeCommission,
    EmployeePerformance,
    EmployeeShopAssignment,
    PayrollRecord,
    PerformanceScore,
    ShopCommissionConfig,
    ShopProfitBasis,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _shop_key(platform_code: Any, shop_id: Any) -> str:
    return f"{str(platform_code or '').lower()}|{str(shop_id or '')}"


def _summary_field(details: Any, *keys: str) -> Any:
    current: Any = details or {}
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


class MonthlySettlementService:
    """月度结算单（只读）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build(self, year_month: str) -> Dict[str, Any]:
        # ---------------------------------------------------------- 店铺绩效
        score_rows = (
            (
                await self.db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.period == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
        score_by_shop: Dict[str, Any] = {}
        for row in score_rows:
            score_by_shop[_shop_key(row.platform_code, row.shop_id)] = row

        # ---------------------------------------------------------- 利润基数
        basis_rows = (
            (
                await self.db.execute(
                    select(ShopProfitBasis).where(
                        ShopProfitBasis.period_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
        basis_by_shop: Dict[str, Any] = {}
        for row in basis_rows:
            key = _shop_key(row.platform_code, row.shop_id)
            current = basis_by_shop.get(key)
            if current is None or (
                not _is_legacy_basis(getattr(current, "basis_version", ""))
                and _is_legacy_basis(getattr(row, "basis_version", ""))
            ):
                basis_by_shop[key] = row

        # ---------------------------------------------------------- 可分配率
        cfg_rows = (
            (
                await self.db.execute(
                    select(ShopCommissionConfig).where(
                        ShopCommissionConfig.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
        cfg_by_shop: Dict[str, Any] = {
            _shop_key(row.platform_code, row.shop_id): row for row in cfg_rows
        }

        # ---------------------------------------------------------- 归属
        assignment_rows = (
            (
                await self.db.execute(
                    select(EmployeeShopAssignment).where(
                        EmployeeShopAssignment.year_month == year_month,
                        EmployeeShopAssignment.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        assignments_by_employee: Dict[str, List[Any]] = {}
        for row in assignment_rows:
            employee_code = str(row.employee_code or "").strip()
            if not employee_code:
                continue
            assignments_by_employee.setdefault(employee_code, []).append(row)

        # ---------------------------------------------------------- 员工绩效
        performance_rows = (
            (
                await self.db.execute(
                    select(EmployeePerformance).where(
                        EmployeePerformance.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
        performance_by_employee = {
            str(row.employee_code or "").strip(): row for row in performance_rows
        }

        commission_rows = (
            (
                await self.db.execute(
                    select(EmployeeCommission).where(
                        EmployeeCommission.year_month == year_month
                    )
                )
            )
            .scalars()
            .all()
        )
        commission_by_employee = {
            str(row.employee_code or "").strip(): row for row in commission_rows
        }

        payroll_rows = (
            (
                await self.db.execute(
                    select(PayrollRecord).where(PayrollRecord.year_month == year_month)
                )
            )
            .scalars()
            .all()
        )
        payroll_by_employee = {
            str(row.employee_code or "").strip(): row for row in payroll_rows
        }

        employee_codes = sorted(
            set(assignments_by_employee)
            | set(performance_by_employee)
            | set(commission_by_employee)
            | set(payroll_by_employee)
        )
        name_by_code: Dict[str, str] = {}
        if employee_codes:
            name_rows = (
                (
                    await self.db.execute(
                        select(Employee.employee_code, Employee.name).where(
                            Employee.employee_code.in_(employee_codes)
                        )
                    )
                )
                .tuples()
                .all()
            )
            name_by_code = {
                str(code): str(name) for code, name in name_rows if code and name
            }

        # ---------------------------------------------------------- 店铺行
        expected_commission_by_shop: Dict[str, float] = {}
        #: 店铺维度的「归属提成比合计」——用来判断是不是「没人配提成比」
        ratio_sum_by_shop: Dict[str, float] = {}
        for employee_code, rows in assignments_by_employee.items():
            perf = performance_by_employee.get(employee_code)
            score_coefficient = _score_coefficient(
                getattr(perf, "performance_score", None)
            )
            for row in rows:
                key = _shop_key(row.platform_code, row.shop_id)
                basis = basis_by_shop.get(key)
                profit_basis_amount = _to_float(
                    getattr(basis, "profit_basis_amount", 0), 0.0
                )
                cfg = cfg_by_shop.get(key)
                alloc_rate = _to_float(
                    getattr(cfg, "allocatable_profit_rate", 0), 0.0
                )
                score = score_by_shop.get(key)
                shop_coefficient = _to_float(
                    getattr(score, "performance_coefficient", None), 1.0
                )
                if getattr(score, "performance_coefficient", None) is None:
                    shop_coefficient = 1.0
                settlement_coefficient = min(
                    shop_coefficient,
                    score_coefficient if score_coefficient is not None else shop_coefficient,
                )
                ratio = _to_float(getattr(row, "commission_ratio", 0), 0.0)
                ratio_sum_by_shop[key] = ratio_sum_by_shop.get(key, 0.0) + ratio
                expected_commission_by_shop[key] = (
                    expected_commission_by_shop.get(key, 0.0)
                    + max(profit_basis_amount, 0.0)
                    * alloc_rate
                    * ratio
                    * settlement_coefficient
                )

        shops: List[Dict[str, Any]] = []
        loss_shop_count = 0
        not_applicable_shop_count = 0
        for key, score in sorted(score_by_shop.items()):
            details = getattr(score, "score_details", None) or {}
            summary = _summary_field(details, "summary") or {}
            profit_detail = _summary_field(details, "profit") or {}
            calculation_status = str(summary.get("calculation_status") or "")
            profit_status = str(profit_detail.get("status") or "")
            basis = basis_by_shop.get(key)
            profit_basis_amount = _to_float(
                getattr(basis, "profit_basis_amount", 0), 0.0
            )
            cfg = cfg_by_shop.get(key)
            is_rate_configured = cfg is not None
            alloc_rate = _to_float(getattr(cfg, "allocatable_profit_rate", 0), 0.0)
            if profit_status == "loss" or profit_basis_amount < 0:
                loss_shop_count += 1
                profit_status = profit_status or "loss"
            if calculation_status == "not_applicable":
                not_applicable_shop_count += 1
            shops.append(
                {
                    "platform_code": str(score.platform_code or "").lower(),
                    "shop_id": score.shop_id,
                    "total_score": _to_float(getattr(score, "total_score", None), 0.0),
                    "rank": getattr(score, "rank", None),
                    "shop_coefficient": _to_float(
                        getattr(score, "performance_coefficient", None), 1.0
                    )
                    if getattr(score, "performance_coefficient", None) is not None
                    else None,
                    "calculation_status": calculation_status or "pending",
                    "profit_status": profit_status or "pending_target",
                    "ranking_pool": str(summary.get("ranking_pool") or ""),
                    "message": str(summary.get("message") or ""),
                    "profit_basis_amount": round(profit_basis_amount, 2),
                    "basis_version": str(getattr(basis, "basis_version", "") or ""),
                    "is_basis_locked": bool(getattr(basis, "is_locked", False)),
                    "allocatable_profit_rate": round(alloc_rate, 6),
                    "is_allocatable_rate_configured": is_rate_configured,
                    "expected_commission": round(
                        expected_commission_by_shop.get(key, 0.0), 2
                    ),
                    "commission_zero_reason": commission_zero_reason(
                        is_rate_configured=is_rate_configured,
                        allocatable_rate=alloc_rate,
                        profit_basis_amount=profit_basis_amount,
                        # 有提成就不报「提成为 0」：必须把实际预计提成传进来
                        estimated_total_commission=expected_commission_by_shop.get(
                            key, 0.0
                        ),
                        has_assignment=key in ratio_sum_by_shop,
                        commission_ratio_sum=ratio_sum_by_shop.get(key),
                    ),
                }
            )

        # ---------------------------------------------------------- 员工行
        employees: List[Dict[str, Any]] = []
        blocking_issues = PerformanceReadinessService.collect_employee_readiness_issues(
            set(assignments_by_employee) | set(payroll_by_employee),
            performance_by_employee,
        )
        issue_by_employee = {
            issue["employee_code"]: issue for issue in blocking_issues
        }
        # 阻断项带上姓名，前端不用再反查 employees[]（避免隐式耦合）。
        for issue in blocking_issues:
            issue["employee_name"] = name_by_code.get(
                issue["employee_code"], issue["employee_code"]
            )
        total_net_salary = 0.0
        total_commission = 0.0
        total_performance_salary = 0.0
        confirmed_count = 0
        draft_count = 0
        for employee_code in employee_codes:
            perf = performance_by_employee.get(employee_code)
            commission = commission_by_employee.get(employee_code)
            payroll = payroll_by_employee.get(employee_code)
            status = str(getattr(perf, "calculation_status", "") or "")
            performance_salary = _to_float(
                getattr(payroll, "performance_salary", 0), 0.0
            )
            commission_amount = _to_float(
                getattr(payroll, "commission", None)
                if payroll is not None
                else getattr(commission, "commission_amount", 0),
                0.0,
            )
            commission_source = (
                "payroll_record"
                if payroll is not None
                else ("employee_commission" if commission is not None else "none")
            )
            net_salary = _to_float(getattr(payroll, "net_salary", 0), 0.0)
            payroll_status = str(getattr(payroll, "status", "") or "")
            if payroll_status == "confirmed":
                confirmed_count += 1
            elif payroll_status == "draft":
                draft_count += 1
            # 合计必须等于「逐行舍入后再求和」，
            # 否则卡片上的合计会和下面的明细求和对不上 1 分钱 ——
            # 那正是这一页要消灭的那类对不上。
            total_net_salary += round(net_salary, 2)
            total_commission += round(commission_amount, 2)
            total_performance_salary += round(performance_salary, 2)
            issue = issue_by_employee.get(employee_code)
            # 提成拆解直接读**已落库**的 ``employee_commissions.calculation_details``，
            # 这里不做任何二次计算 —— 页面上看到的每一分钱都能对上账。
            commission_details = (
                getattr(commission, "calculation_details", None) or {}
            )
            if not isinstance(commission_details, dict):
                commission_details = {}
            score_coefficient = commission_details.get("score_coefficient")
            if score_coefficient is None:
                score_coefficient = _score_coefficient(
                    getattr(perf, "performance_score", None)
                )
            shop_coefficients = commission_details.get("shop_coefficients")
            if not isinstance(shop_coefficients, list):
                shop_coefficients = []
            # 只展示真正产生了提成的店（提成 0 的店不影响「这笔钱怎么来的」）
            shop_breaks = [
                {
                    "shop_key": str(item.get("shop_key") or ""),
                    "commission_ratio": _to_float(item.get("commission_ratio"), 0.0),
                    "allocatable_profit_rate": _to_float(
                        item.get("allocatable_profit_rate"), 0.0
                    ),
                    "profit_basis_amount": _to_float(
                        item.get("profit_basis_amount"), 0.0
                    ),
                    "shop_coefficient": _to_float(item.get("shop_coefficient"), 1.0),
                    "score_coefficient": _to_float(item.get("score_coefficient"), 1.0),
                    "settlement_coefficient": _to_float(
                        item.get("settlement_coefficient"), 1.0
                    ),
                    "limited_by": str(item.get("limited_by") or ""),
                    "commission_amount": round(
                        _to_float(item.get("commission_amount"), 0.0), 2
                    ),
                }
                for item in shop_coefficients
                if isinstance(item, dict)
                and abs(_to_float(item.get("commission_amount"), 0.0)) > 0.004
            ]
            employees.append(
                {
                    "employee_code": employee_code,
                    "employee_name": name_by_code.get(employee_code, employee_code),
                    "performance_score": getattr(perf, "performance_score", None),
                    # 「月度结算系数」= 绩效工资口径的月度系数（按销售额×提成比加权）。
                    # 它**只用于绩效工资**，不代表提成的算法 —— 提成是逐店各算各的。
                    "performance_salary_coefficient": _to_float(
                        getattr(perf, "performance_coefficient", None), 0.0
                    )
                    if getattr(perf, "performance_coefficient", None) is not None
                    else None,
                    # 个人分数档位系数：提成和绩效工资共同的约束项之一
                    "score_coefficient": _to_float(score_coefficient, 0.0)
                    if score_coefficient is not None
                    else None,
                    # 逐店提成拆解：能自己把「240.69」加出来
                    "shop_breaks": shop_breaks,
                    "calculation_status": status or "missing",
                    "performance_source_type": str(
                        getattr(perf, "performance_source_type", "") or ""
                    ),
                    "commission_status": str(
                        getattr(commission, "calculation_status", "") or ""
                    ),
                    "commission_source": commission_source,
                    "commission_amount": round(commission_amount, 2),
                    "performance_salary": round(performance_salary, 2),
                    "net_salary": round(net_salary, 2),
                    "payroll_id": getattr(payroll, "id", None),
                    "payroll_status": payroll_status or "missing",
                    "shop_count": len(assignments_by_employee.get(employee_code, [])),
                    "blocking_issue": issue,
                }
            )

        formal_count = sum(
            1
            for item in employees
            if item["calculation_status"] == "complete"
        )
        not_participating_count = sum(
            1
            for item in employees
            if item["calculation_status"] == "not_participating"
        )

        return {
            "year_month": year_month,
            "summary": {
                "employee_count": len(employees),
                "formal_count": formal_count,
                "not_participating_count": not_participating_count,
                "pending_count": len(blocking_issues),
                "shop_count": len(shops),
                "loss_shop_count": loss_shop_count,
                "not_applicable_shop_count": not_applicable_shop_count,
                "payroll_confirmed_count": confirmed_count,
                "payroll_draft_count": draft_count,
                "total_commission": round(total_commission, 2),
                "total_performance_salary": round(total_performance_salary, 2),
                "total_net_salary": round(total_net_salary, 2),
                "is_settlement_ready": not blocking_issues,
                # 「绩效数据齐了」和「工资单都确认了」是两件事，
                # 分开给，避免把「可以确认」误读成「已经确认」。
                "is_payroll_confirmed": (
                    draft_count == 0 and confirmed_count > 0
                ),
            },
            "employees": employees,
            "shops": shops,
            "blocking_issues": blocking_issues,
        }


def _is_legacy_basis(basis_version: Any) -> bool:
    return str(basis_version or "").strip() == "A_ONLY_V1"


def _score_coefficient(performance_score: Any) -> Optional[float]:
    from backend.services.performance_coefficient import calculate_score_coefficient

    if performance_score is None:
        return None
    return calculate_score_coefficient(performance_score)
