from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from backend.services.personal_performance_scoring_service import (
    PersonalPerformanceScoringService,
)
from modules.core.db import (
    Employee,
    Department,
    EmployeePerformanceAdjustment,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PersonalPerformanceAssignmentSnapshot,
    PersonalPerformanceEmployeeScope,
    PersonalPerformanceEntry,
    PersonalPerformanceMetricCatalog,
    PersonalPerformancePlan,
    Position,
    SalesTarget,
    TargetBreakdown,
)


class PersonalPerformanceWorkbenchConflictError(ValueError):
    """Raised when a stale controlled personal-target plan is saved."""


class PersonalPerformanceWorkbenchService:
    CALCULATION_MODE = "controlled_targets_v1"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _begin_month_mutation(self, year_month: str) -> None:
        lock = PayrollPeriodLockService(self.db)
        await lock.acquire_month_transaction_lock(year_month=year_month)
        await lock.assert_month_mutable(year_month=year_month)

    async def _commit_month_mutation(self, year_month: str) -> None:
        await PayrollPeriodLockService(self.db).assert_month_mutable(year_month=year_month)
        await self.db.commit()

    @staticmethod
    def _clean_code(value: str | None) -> str:
        code = str(value or "").strip()
        if not code:
            raise ValueError("员工标识不能为空")
        return code

    @staticmethod
    def _rule_metric(item: Any, max_score: int) -> dict[str, Any]:
        return {
            "metric_code": item.metric_code,
            "metric_name": item.metric_name,
            "metric_direction": item.metric_direction,
            "input_kind": item.input_kind,
            "default_target_value": item.default_target_value,
            "unit": item.unit,
            "sort_key": item.sort_key,
            "guidance": item.guidance,
            "scoring_rule_version": item.scoring_rule_version,
            "max_score": max_score,
        }

    @staticmethod
    def _entry_payload(entry: Any, metric: dict[str, Any]) -> dict[str, Any]:
        kind = str(metric["input_kind"])
        if kind == "percentage":
            if any(getattr(entry, field, None) is not None for field in ("completed_count", "required_count", "result", "note")):
                raise ValueError("录入字段与百分比指标类型不匹配")
            if getattr(entry, "actual_value", None) is None:
                raise ValueError("百分比指标必须填写实际值")
            return {"actual_value": getattr(entry, "actual_value")}
        if kind == "training_counts":
            if any(getattr(entry, field, None) is not None for field in ("actual_value", "result", "note")):
                raise ValueError("录入字段与培训指标类型不匹配")
            if getattr(entry, "completed_count", None) is None or getattr(entry, "required_count", None) is None:
                raise ValueError("培训指标必须填写已完成和应完成人数")
            return {"completed_count": entry.completed_count, "required_count": entry.required_count}
        if kind == "special_task":
            if any(getattr(entry, field, None) is not None for field in ("actual_value", "completed_count", "required_count")):
                raise ValueError("录入字段与专项任务指标类型不匹配")
            if not getattr(entry, "result", None):
                raise ValueError("专项任务必须选择结果")
            return {"result": entry.result, "note": (str(getattr(entry, "note", "") or "").strip() or None)}
        raise ValueError("个人指标录入类型无效")

    @staticmethod
    def _eligibility(assignments: list[Any], sales_targets: dict[tuple[str, str], Any]) -> list[str]:
        valid = []
        invalid = []
        for assignment in assignments:
            ratio = float(getattr(assignment, "target_allocation_ratio", 0) or 0)
            key = (str(getattr(assignment, "platform_code", "")).lower(), str(getattr(assignment, "shop_id", "")))
            target = sales_targets.get(key)
            if ratio <= 0:
                continue
            if target is None or float(getattr(target, "target_amount", 0) or 0) <= 0:
                invalid.append(f"{key[0]}/{key[1]}")
                continue
            valid.append(f"{key[0]}/{key[1]}")
        return [] if invalid else valid

    @staticmethod
    def _invalid_target_shops(
        assignments: list[Any], sales_targets: dict[tuple[str, str], Any]
    ) -> list[str]:
        invalid = []
        for assignment in assignments:
            if float(getattr(assignment, "target_allocation_ratio", 0) or 0) <= 0:
                continue
            key = (
                str(getattr(assignment, "platform_code", "")).lower(),
                str(getattr(assignment, "shop_id", "")),
            )
            target = sales_targets.get(key)
            if target is None or float(getattr(target, "target_amount", 0) or 0) <= 0:
                invalid.append(f"{key[0]}/{key[1]}")
        return invalid

    @staticmethod
    def _employee_snapshot(employee: Any, department: Any | None, position: Any | None) -> dict[str, Any]:
        return {
            "employee_code": str(employee.employee_code).strip(),
            "employee_name": employee.name,
            "department_name": getattr(department, "department_name", None),
            "position_name": getattr(position, "position_name", None),
        }

    @staticmethod
    def _sales_target_query_parts(year_month: str) -> tuple[list[Any], list[Any]]:
        year, month = (int(part) for part in year_month.split("-"))
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return (
            [
                SalesTarget.target_type == "shop",
                SalesTarget.status == "active",
                SalesTarget.period_start <= end,
                SalesTarget.period_end >= start,
                TargetBreakdown.breakdown_type == "shop",
            ],
            [SalesTarget.period_start.desc(), SalesTarget.created_at.desc(), SalesTarget.id.desc(), TargetBreakdown.id.desc()],
        )

    @staticmethod
    def _select_authoritative_sales_targets(rows: list[Any]) -> dict[tuple[str, str], Any]:
        """Rows are already priority-ordered: never skip a current zero target."""
        authoritative: dict[tuple[str, str], Any] = {}
        for row in rows:
            key = (str(row.platform_code).lower(), str(row.shop_id))
            authoritative.setdefault(key, row)
        return {
            key: row
            for key, row in authoritative.items()
            if float(getattr(row, "target_amount", 0) or 0) > 0
        }

    async def _catalog(self, catalog_version: int | None = None) -> list[Any]:
        if catalog_version is None:
            result = await self.db.execute(
                select(PersonalPerformanceMetricCatalog.catalog_version)
                .where(PersonalPerformanceMetricCatalog.is_active.is_(True))
                .order_by(PersonalPerformanceMetricCatalog.catalog_version.desc())
                .limit(1)
            )
            catalog_version = result.scalar_one_or_none()
        if catalog_version is None:
            return []
        return (await self.db.execute(
            select(PersonalPerformanceMetricCatalog)
            .where(
                PersonalPerformanceMetricCatalog.catalog_version == catalog_version,
                PersonalPerformanceMetricCatalog.is_active.is_(True),
            )
            .order_by(PersonalPerformanceMetricCatalog.sort_key, PersonalPerformanceMetricCatalog.metric_code)
        )).scalars().all()

    async def _plan(self, year_month: str, *, for_update: bool = False) -> Any | None:
        statement = select(PersonalPerformancePlan).where(PersonalPerformancePlan.year_month == year_month)
        if for_update:
            statement = statement.with_for_update()
        return (await self.db.execute(
            statement
        )).scalar_one_or_none()

    async def _assert_no_legacy_data(self, year_month: str) -> None:
        legacy_input = (await self.db.execute(
            select(EmployeePerformanceInput.id).where(
                EmployeePerformanceInput.year_month == year_month,
                EmployeePerformanceInput.status == "active",
            ).limit(1)
        )).scalar_one_or_none()
        legacy_adjustment = (await self.db.execute(
            select(EmployeePerformanceAdjustment.id).where(
                EmployeePerformanceAdjustment.year_month == year_month,
                EmployeePerformanceAdjustment.status == "active",
            ).limit(1)
        )).scalar_one_or_none()
        if legacy_input is not None or legacy_adjustment is not None:
            raise ValueError("本月存在有效旧个人绩效输入或调整，不能切换为受控个人目标模式")

    async def _has_active_legacy_records(self, year_month: str) -> bool:
        legacy_input = (
            await self.db.execute(
                select(EmployeePerformanceInput.id)
                .where(
                    EmployeePerformanceInput.year_month == year_month,
                    EmployeePerformanceInput.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if legacy_input is not None:
            return True
        legacy_adjustment = (
            await self.db.execute(
                select(EmployeePerformanceAdjustment.id)
                .where(
                    EmployeePerformanceAdjustment.year_month == year_month,
                    EmployeePerformanceAdjustment.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return legacy_adjustment is not None

    @staticmethod
    def _assert_version(plan: Any, expected: int | None) -> None:
        if expected is not None and int(getattr(plan, "version", 0)) != int(expected):
            raise PersonalPerformanceWorkbenchConflictError("个人绩效规则已被其他用户更新，请刷新后重试")

    async def get_workbench(self, year_month: str) -> dict[str, Any]:
        plan = await self._plan(year_month)
        if plan is None:
            catalog = await self._catalog()
            has_legacy_records = await self._has_active_legacy_records(year_month)
            return {
                "year_month": year_month,
                "calculation_mode": "legacy_inputs",
                "plan_version": None,
                "scope_confirmed": False,
                "metrics": [self._rule_metric(item, 0) for item in catalog],
                "legacy_read_only": has_legacy_records,
                "has_legacy_records": has_legacy_records,
            }
        metrics = list((getattr(plan, "rule_snapshot", {}) or {}).get("metrics", []))
        return {
            "year_month": year_month,
            "calculation_mode": self.CALCULATION_MODE,
            "plan_version": plan.version,
            "scope_confirmed": plan.scope_confirmed_at is not None,
            "metrics": metrics,
            "legacy_read_only": False,
            "has_legacy_records": False,
        }

    async def apply(self, request: Any, username: str | None = None) -> dict[str, Any]:
        await self._begin_month_mutation(request.year_month)
        plan = await self._plan(request.year_month, for_update=True)
        if plan is not None:
            self._assert_version(plan, getattr(request, "expected_plan_version", None))
            if plan.scope_confirmed_at is not None:
                raise ValueError("店铺范围已确认，请先撤销范围后再修改个人目标规则")
        else:
            await self._assert_no_legacy_data(request.year_month)
        catalog = await self._catalog()
        by_code = {str(item.metric_code): item for item in catalog}
        enabled = [item for item in request.metrics if bool(item.is_enabled)]
        if not enabled:
            raise ValueError("至少启用一项个人运营指标")
        unknown = [item.metric_code for item in request.metrics if item.metric_code not in by_code]
        if unknown:
            raise ValueError(f"个人指标不在受控目录中: {', '.join(unknown)}")
        allocations = PersonalPerformanceScoringService.allocate_integer_budget([
            {"metric_code": item.metric_code, "sort_key": by_code[item.metric_code].sort_key}
            for item in enabled
        ])
        snapshot = {"catalog_version": catalog[0].catalog_version, "metrics": [self._rule_metric(by_code[item.metric_code], allocations[item.metric_code]) for item in enabled]}
        now = datetime.now(timezone.utc)
        if plan is None:
            plan = PersonalPerformancePlan(year_month=request.year_month, calculation_mode=self.CALCULATION_MODE, catalog_version=catalog[0].catalog_version, scoring_model_version=self.CALCULATION_MODE, rule_snapshot=snapshot, version=1, created_by=username, updated_by=username)
            self.db.add(plan)
        else:
            plan.catalog_version = catalog[0].catalog_version
            plan.scoring_model_version = self.CALCULATION_MODE
            plan.rule_snapshot = snapshot
            plan.version += 1
            plan.updated_by = username
            plan.updated_at = now
        await self._commit_month_mutation(request.year_month)
        return await self.get_workbench(request.year_month)

    async def _active_employees(self) -> list[Any]:
        return (await self.db.execute(
            select(Employee, Department, Position)
            .outerjoin(Department, Department.id == Employee.department_id)
            .outerjoin(Position, Position.id == Employee.position_id)
            .where(Employee.status.in_(("active", "probation")))
            .order_by(Employee.employee_code)
        )).all()

    async def _assignments(self, year_month: str) -> dict[str, list[Any]]:
        rows = (await self.db.execute(select(EmployeeShopAssignment).where(EmployeeShopAssignment.year_month == year_month, EmployeeShopAssignment.status == "active"))).scalars().all()
        result: dict[str, list[Any]] = {}
        for row in rows:
            result.setdefault(str(row.employee_code).strip(), []).append(row)
        return result

    async def _sales_targets(self, year_month: str) -> dict[tuple[str, str], Any]:
        conditions, ordering = self._sales_target_query_parts(year_month)
        rows = (await self.db.execute(
            select(TargetBreakdown).join(SalesTarget, SalesTarget.id == TargetBreakdown.target_id)
            .where(*conditions).order_by(*ordering)
        )).scalars().all()
        return self._select_authoritative_sales_targets(rows)

    async def get_scope(self, year_month: str) -> dict[str, Any]:
        plan = await self._plan(year_month)
        if plan is None:
            return {"year_month": year_month, "plan_version": None, "scope_confirmed": False, "employees": []}
        stored = (await self.db.execute(select(PersonalPerformanceEmployeeScope).where(PersonalPerformanceEmployeeScope.plan_id == plan.id))).scalars().all()
        if plan.scope_confirmed_at is not None:
            return {"year_month": year_month, "plan_version": plan.version, "scope_confirmed": True, "employees": [{"employee_code": row.employee_code, "employee_name": row.employee_name_snapshot, "department_name": row.department_name_snapshot, "position_name": row.position_name_snapshot, "is_included": row.is_included, "exclusion_note": row.exclusion_note, "eligibility_status": "eligible" if row.is_included else "not_participating", "blocking_reasons": []} for row in stored]}
        assignments = await self._assignments(year_month)
        targets = await self._sales_targets(year_month)
        return {"year_month": year_month, "plan_version": plan.version, "scope_confirmed": False, "employees": [self._candidate_employee(employee, department, position, assignments.get(str(employee.employee_code).strip(), []), targets) for employee, department, position in await self._active_employees()]}

    @classmethod
    def _candidate_employee(cls, employee: Any, department: Any | None, position: Any | None, assignments: list[Any], targets: dict[tuple[str, str], Any]) -> dict[str, Any]:
        eligible = cls._eligibility(assignments, targets)
        invalid_shops = cls._invalid_target_shops(assignments, targets)
        reasons = (
            []
            if eligible
            else [
                "缺少有效店铺归属、正归属比例或正销售目标"
                + (f": {', '.join(invalid_shops)}" if invalid_shops else "")
            ]
        )
        return {**cls._employee_snapshot(employee, department, position), "is_included": bool(eligible), "exclusion_note": None, "eligibility_status": "eligible" if eligible else "blocked", "blocking_reasons": reasons}

    async def apply_scope(self, request: Any, username: str | None = None) -> dict[str, Any]:
        await self._begin_month_mutation(request.year_month)
        plan = await self._plan(request.year_month, for_update=True)
        if plan is None:
            raise ValueError("请先保存个人运营目标规则")
        self._assert_version(plan, request.expected_plan_version)
        if plan.scope_confirmed_at is not None:
            raise ValueError("本月员工范围已确认，请先撤销范围")
        employees = {str(employee.employee_code).strip(): (employee, department, position) for employee, department, position in await self._active_employees()}
        requested = {self._clean_code(item.employee_code): item for item in request.employees}
        unknown = set(requested) - set(employees)
        if unknown:
            raise ValueError("员工必须来自当前在职员工主数据")
        assignments, targets = await self._assignments(request.year_month), await self._sales_targets(request.year_month)
        await self.db.execute(delete(PersonalPerformanceEmployeeScope).where(PersonalPerformanceEmployeeScope.plan_id == plan.id))
        now = datetime.now(timezone.utc)
        for code, (employee, department, position) in employees.items():
            item = requested.get(code)
            included = True if item is None else bool(item.is_included)
            employee_assignments = assignments.get(code, [])
            if included and not self._eligibility(employee_assignments, targets):
                invalid_shops = self._invalid_target_shops(employee_assignments, targets)
                detail = f"，无效销售目标店铺: {', '.join(invalid_shops)}" if invalid_shops else ""
                raise ValueError(f"员工 {code} 缺少有效店铺归属或正销售目标，不能参与正式个人绩效{detail}")
            identity = self._employee_snapshot(employee, department, position)
            scope = PersonalPerformanceEmployeeScope(plan_id=plan.id, employee_code=code, employee_name_snapshot=identity["employee_name"], department_name_snapshot=identity["department_name"], position_name_snapshot=identity["position_name"], is_included=included, exclusion_note=None if included else (str(getattr(item, 'exclusion_note', '') or '').strip() or None), snapshot_version=1, confirmed_at=now, confirmed_by=username, created_by=username, updated_by=username)
            self.db.add(scope)
            await self.db.flush()
            if included:
                for assignment in employee_assignments:
                    key = (str(assignment.platform_code).lower(), str(assignment.shop_id))
                    target = targets.get(key)
                    if float(getattr(assignment, "target_allocation_ratio", 0) or 0) <= 0 or target is None:
                        continue
                    self.db.add(PersonalPerformanceAssignmentSnapshot(scope_id=scope.id, source_assignment_id=assignment.id, platform_code=key[0], shop_id=key[1], assignment_ratio_snapshot=assignment.target_allocation_ratio, role_snapshot=assignment.role, sales_target_breakdown_id_snapshot=target.id, sales_target_amount_snapshot=target.target_amount))
        plan.scope_confirmed_at, plan.scope_confirmed_by = now, username
        plan.version += 1
        await self._commit_month_mutation(request.year_month)
        return await self.get_scope(request.year_month)

    async def _scope_rows(self, plan_id: int) -> list[Any]:
        return (await self.db.execute(select(PersonalPerformanceEmployeeScope).where(PersonalPerformanceEmployeeScope.plan_id == plan_id))).scalars().all()

    async def get_entries(self, year_month: str) -> dict[str, Any]:
        plan = await self._plan(year_month)
        if plan is None or plan.scope_confirmed_at is None:
            return {"year_month": year_month, "scope_confirmed": False, "employees": [], "completion": {"completed": 0, "pending": 0}}
        metrics = list((plan.rule_snapshot or {}).get("metrics", []))
        scopes = [row for row in await self._scope_rows(plan.id) if row.is_included]
        scope_ids = [row.id for row in scopes]
        entries = (await self.db.execute(select(PersonalPerformanceEntry).where(PersonalPerformanceEntry.scope_id.in_(scope_ids)))).scalars().all() if scope_ids else []
        by_key = {(row.scope_id, row.metric_code): row for row in entries}
        result, completed = [], 0
        for scope in scopes:
            rendered = []
            complete = True
            for metric in metrics:
                entry = by_key.get((scope.id, metric["metric_code"]))
                score, detail = PersonalPerformanceScoringService.calculate_metric_score(metric=metric, payload=getattr(entry, "input_payload", None))
                complete = complete and score is not None
                rendered.append({"metric_code": metric["metric_code"], "metric_name": metric["metric_name"], "input_kind": metric["input_kind"], "input_payload": getattr(entry, "input_payload", {}) or {}, "target_value": metric.get("default_target_value"), "max_score": metric["max_score"], "auto_score": score, "status": "completed" if score is not None else "pending", "guidance": metric.get("guidance"), "formula": detail.get("message")})
            completed += int(complete)
            result.append({"employee_code": scope.employee_code, "employee_name": scope.employee_name_snapshot, "status": "completed" if complete else "pending", "metrics": rendered})
        return {"year_month": year_month, "scope_confirmed": True, "employees": result, "completion": {"completed": completed, "pending": len(scopes) - completed}}

    async def apply_entries(self, request: Any, username: str | None = None) -> dict[str, Any]:
        await self._begin_month_mutation(request.year_month)
        plan = await self._plan(request.year_month, for_update=True)
        if plan is None or plan.scope_confirmed_at is None:
            raise ValueError("请先确认本月参与员工范围")
        self._assert_version(plan, request.expected_plan_version)
        scopes = {row.employee_code: row for row in await self._scope_rows(plan.id) if row.is_included}
        metrics = {item["metric_code"]: item for item in (plan.rule_snapshot or {}).get("metrics", [])}
        existing = (await self.db.execute(select(PersonalPerformanceEntry).where(PersonalPerformanceEntry.scope_id.in_([row.id for row in scopes.values()])))).scalars().all() if scopes else []
        by_key = {(row.scope_id, row.metric_code): row for row in existing}
        for item in request.entries:
            code = self._clean_code(item.employee_code)
            scope = scopes.get(code)
            if scope is None:
                raise ValueError("该员工未参与本月个人绩效，不能录入")
            metric = metrics.get(item.metric_code)
            if metric is None:
                raise ValueError("个人录入指标不存在或未启用")
            payload = self._entry_payload(item, metric)
            score, _ = PersonalPerformanceScoringService.calculate_metric_score(metric=metric, payload=payload)
            row = by_key.get((scope.id, item.metric_code))
            if row is None:
                row = PersonalPerformanceEntry(scope_id=scope.id, metric_code=item.metric_code, created_by=username)
                self.db.add(row)
            row.input_payload, row.metric_snapshot, row.auto_score, row.completion_status, row.updated_by = payload, metric, score, "completed" if score is not None else "pending", username
        await self._commit_month_mutation(request.year_month)
        return await self.get_entries(request.year_month)

    async def revoke_scope(self, year_month: str, expected_plan_version: int) -> dict[str, Any]:
        await self._begin_month_mutation(year_month)
        plan = await self._plan(year_month, for_update=True)
        if plan is None:
            raise ValueError("本月没有个人运营目标规则")
        self._assert_version(plan, expected_plan_version)
        scope_ids = select(PersonalPerformanceEmployeeScope.id).where(PersonalPerformanceEmployeeScope.plan_id == plan.id)
        await self.db.execute(delete(PersonalPerformanceEntry).where(PersonalPerformanceEntry.scope_id.in_(scope_ids)))
        await self.db.execute(delete(PersonalPerformanceAssignmentSnapshot).where(PersonalPerformanceAssignmentSnapshot.scope_id.in_(scope_ids)))
        await self.db.execute(delete(PersonalPerformanceEmployeeScope).where(PersonalPerformanceEmployeeScope.plan_id == plan.id))
        plan.scope_confirmed_at = plan.scope_confirmed_by = None
        plan.version += 1
        await self._commit_month_mutation(year_month)
        return await self.get_scope(year_month)
