from __future__ import annotations

from calendar import monthrange
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    EmployeePerformance,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PersonalPerformanceEmployeeScope,
    PersonalPerformancePlan,
    PayrollRecord,
    PerformanceScore,
    SalaryStructure,
)


class PerformanceReadinessError(ValueError):
    """Raised before payroll or monthly settlement can write incomplete performance data."""


class PerformanceReadinessService:
    #: 明确「不参与考核」的状态。这类员工没有店铺归属、也没有个人绩效指标，
    #: 但他们**不是**「待补数据」，因此不阻断整月工资单确认与月结。
    NON_BLOCKING_STATUSES = frozenset({"not_participating"})

    #: 绩效状态 -> (可读说明, 下一步动作提示)
    STATUS_HINTS: dict[str, tuple[str, str]] = {
        "pending_personal_input": (
            "待补个人绩效指标",
            "请到「个人绩效工作台」录入该员工当月的个人指标",
        ),
        "pending_store_performance": (
            "待补店铺绩效",
            "请检查该员工负责店铺当月的经营数据与绩效计算结果",
        ),
        "pending_scope": (
            "个人绩效范围未确认",
            "请到「个人绩效工作台」确认本月考核人员范围",
        ),
        "missing": (
            "缺少个人绩效记录",
            "请先执行当月绩效计算，生成该员工的绩效结果",
        ),
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    def _describe_employee_status(cls, status: str | None) -> str:
        label, action = cls.STATUS_HINTS.get(
            str(status or ""),
            (str(status or "待计算"), "请先执行当月绩效计算"),
        )
        return f"{label}（{action}）"

    @classmethod
    def collect_employee_readiness_issues(
        cls, employee_codes: set[str], rows_by_employee: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """列出**还没就绪**的员工，每人一条「缺什么、去哪补」。

        不抛错 —— 给「月度结算单」页面用：
        一眼看到「谁卡住了、缺什么、下一步去哪补」，
        而不是只看到一个「绩效尚未完成，无法结算」。

        与 :meth:`assert_employee_rows_ready` 用的是同一套判定口径，
        页面显示的阻断项和真正会阻断的清单不会不一致。
        """
        issues: list[dict[str, Any]] = []
        for employee_code in sorted(employee_codes):
            row = rows_by_employee.get(employee_code)
            if row is None:
                issues.append(
                    {
                        "employee_code": employee_code,
                        "status": "missing",
                        "reason": "缺少个人绩效记录",
                        "action": "请先执行当月绩效计算，生成该员工的绩效结果",
                    }
                )
                continue
            status = getattr(row, "calculation_status", None)
            score = getattr(row, "performance_score", None)
            # Pre-migration callers may return a lightweight row without the new
            # status columns. Migrated rows always carry an explicit status.
            if status is None and score is not None:
                continue
            if status in cls.NON_BLOCKING_STATUSES:
                # 明确不参与考核：不阻断整月结算。
                continue
            if status == "complete" and score is not None:
                continue
            label, action = cls.STATUS_HINTS.get(
                str(status or ""),
                (str(status or "待计算"), "请先执行当月绩效计算"),
            )
            issues.append(
                {
                    "employee_code": employee_code,
                    "status": str(status or "missing"),
                    "reason": label,
                    "action": action,
                }
            )
        return issues

    @classmethod
    def assert_employee_rows_ready(
        cls, employee_codes: set[str], rows_by_employee: dict[str, Any]
    ) -> None:
        pending = [
            f"{issue['employee_code']}:{issue['reason']}"
            for issue in cls.collect_employee_readiness_issues(
                employee_codes, rows_by_employee
            )
        ]
        if pending:
            raise PerformanceReadinessError(
                "绩效尚未完成，无法结算：" + "；".join(pending)
            )

    @classmethod
    def assert_controlled_employee_rows_ready(
        cls, scopes: list[Any], rows_by_employee: dict[str, Any]
    ) -> None:
        included_codes = {
            str(getattr(scope, "employee_code", "") or "").strip()
            for scope in scopes
            if bool(getattr(scope, "is_included", False))
        }
        non_controlled = [
            employee_code
            for employee_code in sorted(included_codes)
            if (
                rows_by_employee.get(employee_code) is not None
                and getattr(
                    rows_by_employee[employee_code], "performance_source_type", None
                )
                not in {None, "controlled_targets_v1"}
            )
        ]
        if non_controlled:
            raise PerformanceReadinessError(
                "controlled target result required: " + ", ".join(non_controlled)
            )
        cls.assert_employee_rows_ready(included_codes, rows_by_employee)

    @staticmethod
    def _is_formal_shop_score(score: Any) -> bool:
        details = getattr(score, "score_details", None) or {}
        summary = details.get("summary", {}) if isinstance(details, dict) else {}
        return bool(
            summary.get("calculation_status") == "complete"
            and summary.get("formal_ready") is True
            and summary.get("ranking_pool") == "official"
        )

    @staticmethod
    def _is_not_applicable_shop_score(score: Any) -> bool:
        """当月不参与考核的店铺（例如没有任何经营数据）不阻断整月结算。"""
        details = getattr(score, "score_details", None) or {}
        summary = details.get("summary", {}) if isinstance(details, dict) else {}
        return summary.get("calculation_status") == "not_applicable"

    @staticmethod
    def _describe_shop_status(score: Any) -> str:
        if score is None:
            return (
                "当月没有生成店铺绩效记录"
                "（请检查该店是否缺当月销售目标、经营数据或运营绩效配置）"
            )
        details = getattr(score, "score_details", None) or {}
        if not isinstance(details, dict):
            return "店铺绩效状态未知"
        summary = details.get("summary", {}) or {}
        profit = details.get("profit", {}) or {}
        operation = details.get("operation", {}) or {}
        if profit.get("status") == "loss":
            return "本店本月结算利润为负（亏损），需确认亏损口径"
        if profit.get("status") == "pending_target":
            return "未配置利润目标（请到「店铺目标」补齐当月利润目标）"
        if profit.get("status") == "forecast":
            return "结算利润基数尚未锁定（请先完成人力成本分摊并锁定利润基数）"
        if operation.get("status") not in (None, "calculated"):
            return "运营绩效尚未完成（请到「运营绩效工作台」录入并确认范围）"
        return summary.get("message") or "店铺绩效尚未正式完成"

    @staticmethod
    def shop_dependent_employee_codes(rows_by_employee: dict[str, Any]) -> set[str]:
        """Personal-input results are complete without a corresponding shop score."""
        return {
            employee_code
            for employee_code, row in rows_by_employee.items()
            if getattr(row, "performance_source_type", None) != "personal_inputs"
        }

    async def assert_month_performance_ready(
        self,
        year_month: str,
        *,
        employee_codes: set[str] | None = None,
    ) -> None:
        plan = (
            await self.db.execute(
                select(PersonalPerformancePlan).where(
                    PersonalPerformancePlan.year_month == year_month
                )
            )
        ).scalar_one_or_none()
        if (
            plan is not None
            and getattr(plan, "calculation_mode", None) == "controlled_targets_v1"
        ):
            scopes = (
                (
                    await self.db.execute(
                        select(PersonalPerformanceEmployeeScope).where(
                            PersonalPerformanceEmployeeScope.plan_id == plan.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            if getattr(plan, "scope_confirmed_at", None) is None:
                raise PerformanceReadinessError(
                    "personal performance scope is not confirmed"
                )
            if employee_codes is not None:
                requested_codes = {
                    str(code).strip() for code in employee_codes if str(code).strip()
                }
                scopes = [
                    scope for scope in scopes if scope.employee_code in requested_codes
                ]
            included_codes = {
                str(scope.employee_code).strip()
                for scope in scopes
                if bool(getattr(scope, "is_included", False))
            }
            if not included_codes:
                return
            performance_rows = (
                (
                    await self.db.execute(
                        select(EmployeePerformance).where(
                            EmployeePerformance.year_month == year_month,
                            EmployeePerformance.employee_code.in_(included_codes),
                        )
                    )
                )
                .scalars()
                .all()
            )
            self.assert_controlled_employee_rows_ready(
                scopes,
                {str(row.employee_code).strip(): row for row in performance_rows},
            )
            return

        period_start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date()
        period_end = period_start.replace(
            day=monthrange(period_start.year, period_start.month)[1]
        )
        assignments = (
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
        inputs = (
            (
                await self.db.execute(
                    select(EmployeePerformanceInput).where(
                        EmployeePerformanceInput.year_month == year_month,
                        EmployeePerformanceInput.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        salaries = (
            (
                await self.db.execute(
                    select(SalaryStructure).where(
                        SalaryStructure.status == "active",
                        SalaryStructure.effective_date <= period_end,
                    )
                )
            )
            .scalars()
            .all()
        )
        payrolls = (
            (
                await self.db.execute(
                    select(PayrollRecord).where(
                        PayrollRecord.year_month == year_month,
                    )
                )
            )
            .scalars()
            .all()
        )

        month_employee_codes = {
            str(getattr(row, "employee_code", "") or "").strip()
            for row in [*assignments, *inputs, *salaries, *payrolls]
            if str(getattr(row, "employee_code", "") or "").strip()
        }
        if employee_codes is not None:
            requested_codes = {
                str(employee_code).strip()
                for employee_code in employee_codes
                if str(employee_code).strip()
            }
            month_employee_codes &= requested_codes
        if not month_employee_codes:
            return
        performance_result = await self.db.execute(
            select(EmployeePerformance).where(
                EmployeePerformance.year_month == year_month,
                EmployeePerformance.employee_code.in_(month_employee_codes),
            )
        )
        performance_rows = performance_result.scalars().all()
        if not performance_rows:
            scalar_one_or_none = getattr(performance_result, "scalar_one_or_none", None)
            if callable(scalar_one_or_none):
                legacy_row = scalar_one_or_none()
                if legacy_row is not None:
                    performance_rows = [legacy_row]
        rows_by_employee = {
            str(
                getattr(row, "employee_code", None) or next(iter(month_employee_codes))
            ): row
            for row in performance_rows
        }
        self.assert_employee_rows_ready(month_employee_codes, rows_by_employee)
        shop_dependent_codes = self.shop_dependent_employee_codes(rows_by_employee)

        shop_keys = {
            (
                str(getattr(row, "platform_code", "") or "").lower(),
                str(getattr(row, "shop_id", "") or ""),
            )
            for row in assignments
            if str(getattr(row, "employee_code", "") or "").strip()
            in shop_dependent_codes
        }
        if not shop_keys:
            return
        score_rows = (
            (
                await self.db.execute(
                    select(PerformanceScore).where(
                        PerformanceScore.period == year_month,
                    )
                )
            )
            .scalars()
            .all()
        )
        scores_by_shop = {
            (str(row.platform_code or "").lower(), str(row.shop_id or "")): row
            for row in score_rows
        }
        pending_shops = []
        for platform_code, shop_id in sorted(shop_keys):
            score = scores_by_shop.get((platform_code, shop_id))
            if self._is_not_applicable_shop_score(score):
                # 当月不参与考核的店铺，不阻断整月结算。
                continue
            if self._is_formal_shop_score(score):
                continue
            pending_shops.append(
                f"{platform_code}|{shop_id}（{self._describe_shop_status(score)}）"
            )
        if pending_shops:
            raise PerformanceReadinessError(
                "店铺绩效尚未正式完成，无法结算：" + "；".join(pending_shops)
            )
