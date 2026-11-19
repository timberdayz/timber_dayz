"""
HR - 员工档案与我的信息
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.models.database import get_async_db
from backend.dependencies.auth import get_current_user, is_admin_user
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger

logger = get_logger(__name__)
from backend.schemas import MyIncomeResponse, IncomeCalculationResponse
from backend.schemas.hr import (
    EmployeeCreate,
    EmployeeMergeRequest,
    EmployeeOffboardRequest,
    EmployeeOffboardResponse,
    EmployeeRegularizeRequest,
    EmployeeResponse,
    EmployeeUpdate,
    EmployeeVisitorPromotionRequest,
    MeProfileUpdate,
)
from backend.services.audit_service import audit_service
from backend.services.hr_employee_lifecycle import (
    EMPLOYEE_IDENTITY_VOCABULARY,
    employee_identity,
    employee_status,
)
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.base_service import provide_service
from backend.services.labor_cost_policy_service import LaborCostPolicyService
from backend.services.payroll_period_lock_service import PAYROLL_LOCKED_STATUSES
from backend.utils.year_month_utils import year_month_to_first_day
from modules.core.db import (
    Employee,
    Department,
    DimUser,
    MonthlyProfitPayrollSnapshot,
    MonthlyProfitSettlement,
    PayrollRecord,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceInput,
    EmployeePerformanceAdjustment,
    EmployeeShopAssignment,
    ShopCommissionConfig,
    PerformanceScore,
    ShopProfitBasis,
    Position,
    PersonalPerformanceAssignmentSnapshot,
    PersonalPerformanceEmployeeScope,
    PersonalPerformancePlan,
)

router = APIRouter(prefix="/api/hr", tags=["HR-员工档案"])

# ============================================================================
# 员工管理API
# ============================================================================


def _audit_performance_inputs(
    *, legacy_rows: list[Any], employee_performance: Any | None
) -> list[dict[str, Any]]:
    if (
        getattr(employee_performance, "performance_source_type", None)
        == "controlled_targets_v1"
    ):
        details = getattr(employee_performance, "calculation_details", None) or {}
        entries = (
            details.get("personal_target_entries", [])
            if isinstance(details, dict)
            else []
        )
        result = []
        for entry in entries:
            payload = dict(entry.get("input_payload") or {})
            actual = payload.get("actual_value")
            result.append(
                {
                    "metric_code": entry.get("metric_code"),
                    "metric_name": entry.get("metric_name"),
                    "metric_direction": entry.get("metric_direction"),
                    "target_value": (
                        float(entry["target_value"])
                        if entry.get("target_value") is not None
                        else None
                    ),
                    "achieved_value": float(actual) if actual is not None else None,
                    "max_score": (
                        float(entry["max_score"])
                        if entry.get("max_score") is not None
                        else None
                    ),
                    "manual_score_enabled": False,
                    "manual_score_value": None,
                    "auto_score": (
                        float(entry["auto_score"])
                        if entry.get("auto_score") is not None
                        else None
                    ),
                    "completion_status": entry.get("completion_status"),
                    "input_payload": payload,
                    "source": "controlled_targets_v1",
                    "reason": entry.get("formula"),
                }
            )
        return result
    return [
        {
            "metric_code": row.metric_code,
            "metric_name": row.metric_name,
            "metric_direction": row.metric_direction,
            "target_value": float(row.target_value or 0),
            "achieved_value": float(row.achieved_value or 0),
            "max_score": float(row.max_score or 0),
            "manual_score_enabled": bool(row.manual_score_enabled),
            "manual_score_value": (
                float(row.manual_score_value)
                if row.manual_score_value is not None
                else None
            ),
            "source": row.source,
            "reason": row.reason,
        }
        for row in legacy_rows
    ]


def _display_employee_performance(employee_performance: Any) -> dict[str, Any]:
    details = getattr(employee_performance, "calculation_details", None) or {}
    display_details = dict(details) if isinstance(details, dict) else {}
    for field in (
        "store_base_score",
        "store_weighted_contribution",
        "personal_target_score",
        "final_score",
    ):
        if display_details.get(field) is not None:
            display_details[field] = round(float(display_details[field]), 1)
    if isinstance(display_details.get("personal_metric_scores"), dict):
        display_details["personal_metric_scores"] = {
            code: round(float(score), 1)
            for code, score in display_details["personal_metric_scores"].items()
        }
    score = getattr(employee_performance, "performance_score", None)
    return {
        "actual_sales": round(
            float(getattr(employee_performance, "actual_sales", 0) or 0), 2
        ),
        "achievement_rate": round(
            float(getattr(employee_performance, "achievement_rate", 0) or 0), 4
        ),
        "performance_score": round(float(score), 1) if score is not None else None,
        "calculation_status": getattr(employee_performance, "calculation_status", None),
        "performance_source_type": getattr(
            employee_performance, "performance_source_type", None
        ),
        "calculation_details": display_details,
        "calculated_at": (
            getattr(employee_performance, "calculated_at", None).isoformat()
            if getattr(employee_performance, "calculated_at", None)
            else None
        ),
    }


async def _username_for_user_id(
    db: AsyncSession, user_id: Optional[int]
) -> Optional[str]:
    """根据 dim_users.user_id 查询 username，用于 EmployeeResponse.username"""
    if not user_id:
        return None
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    return user.username if user else None


async def _department_name_map(
    db: AsyncSession, department_ids: List[Optional[int]]
) -> Dict[int, str]:
    """批量取部门名（``a_class.departments.department_name``）。

    ⚠️ **一次查询批量取**，不逐行查（N+1）。
    """
    ids = {int(item) for item in department_ids if item is not None}
    if not ids:
        return {}
    result = await db.execute(
        select(Department.id, Department.department_name).where(Department.id.in_(ids))
    )
    return {row[0]: row[1] for row in result.all()}


def _validated_identity_filter(identity_type: Any) -> Optional[str]:
    """校验 ``identity_type`` 查询参数（``employee`` / ``visitor``；不传 = 全部）。

    ⚠️ 直接以 Python 函数方式调用（不走 FastAPI）时，``Query(None, ...)`` 的
    默认值是 ``params.Query`` 对象而不是 ``None`` ⇒ 这里一律按「未传」处理。
    """
    if identity_type is None or not isinstance(identity_type, str):
        return None
    value = str(identity_type).strip()
    if not value:
        return None
    if value not in EMPLOYEE_IDENTITY_VOCABULARY:
        raise ValueError(
            f"用工身份只允许 {'/'.join(EMPLOYEE_IDENTITY_VOCABULARY)}，收到: {value}"
        )
    return value


#: 访客档案合并到正式员工时，可以搬运的联系方式字段。
MERGEABLE_CONTACT_FIELDS = (
    "phone",
    "email",
    "address",
    "emergency_contact",
    "emergency_phone",
)


def _merge_employee_contact_fields(target: Any, source: Any) -> List[str]:
    """把访客（source）的联系方式并进正式员工（target）。

    ⚠️ **仅当 target 对应字段为空时才搬** —— 绝不覆盖 target 已有的值。
    （访客档案常常只填了手机号；正式员工的邮箱/地址是 HR 维护的，
    覆盖掉就是拿脏数据盖掉真数据。）

    返回实际搬运了的字段名列表（便于审计留痕）。
    """
    moved: List[str] = []
    for field in MERGEABLE_CONTACT_FIELDS:
        target_value = getattr(target, field, None)
        source_value = getattr(source, field, None)
        if source_value is None or str(source_value).strip() == "":
            continue
        if target_value is not None and str(target_value).strip() != "":
            continue
        setattr(target, field, source_value)
        moved.append(field)
    return moved


@router.get("/me/profile", response_model=EmployeeResponse)
async def get_me_profile(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """我的档案：当前登录用户关联的员工档案；未关联时首次访问自动创建最小员工并关联（系统主要面向内部员工，注册并登录即可用）。路由须在 /employees/{employee_code} 之前。"""
    result = await db.execute(
        select(Employee).where(Employee.user_id == current_user.user_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        # 首次访问自动创建最小员工并关联
        employee_code = await _generate_employee_code(db)
        name = (current_user.full_name or current_user.username or "员工").strip()
        if len(name) > 128:
            name = name[:128]
        employee = Employee(
            employee_code=employee_code,
            name=name,
            user_id=current_user.user_id,
            status="active",
            employee_identity_type="visitor",
            email=current_user.email,
        )
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
        logger.info(
            f"我的档案自动创建员工: {employee_code} (user_id={current_user.user_id})"
        )
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


@router.put("/me/profile", response_model=EmployeeResponse)
async def put_me_profile(
    body: MeProfileUpdate,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """我的档案：仅接受白名单字段 phone/email/address/emergency_contact/emergency_phone。"""
    result = await db.execute(
        select(Employee).where(Employee.user_id == current_user.user_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        return error_response(
            ErrorCode.DATA_NOT_FOUND,
            "您尚未关联员工档案，请联系管理员",
            status_code=404,
        )
    update_data = body.model_dump(exclude_unset=True)
    for key in ("phone", "email", "address", "emergency_contact", "emergency_phone"):
        if key in update_data:
            setattr(employee, key, update_data[key])
    employee.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(employee)
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


async def _log_me_income_access(
    request: Request,
    user_id: int,
    period: Optional[str],
    result_status: str,
    db: AsyncSession,
) -> None:
    """记录「我的收入」访问审计（仅 endpoint/user_id/request_time/result_status，不记录敏感字段）。"""
    try:
        from backend.services.audit_service import audit_service

        client_host = request.client.host if request.client else ""
        user_agent = (request.headers.get("user-agent") or "")[:500]
        await audit_service.log_action(
            user_id=user_id,
            action="view",
            resource="me/income",
            ip_address=client_host,
            user_agent=user_agent,
            resource_id=period,
            details={"result_status": result_status},
            db=db,
        )
    except Exception as e:
        logger.warning("me/income audit log write failed: %s", e)


@router.get("/me/income", response_model=MyIncomeResponse)
async def get_my_income(
    request: Request,
    year_month: Optional[str] = Query(None, description="月份(YYYY-MM)，不填则当月"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """我的收入：根据当前用户关联的员工返回收入数据；未关联时返回 200 + linked: false。仅允许本人访问，记录访问审计（不记录敏感薪资字段）。"""
    current_user_id = current_user.user_id
    result = await db.execute(
        select(Employee).where(Employee.user_id == current_user_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        await _log_me_income_access(
            request, current_user_id, year_month, "linked_false", db
        )
        return MyIncomeResponse(linked=False)
    if getattr(employee, "employee_identity_type", None) not in {None, "employee"}:
        await _log_me_income_access(
            request, current_user_id, year_month, "linked_false", db
        )
        return MyIncomeResponse(linked=False)
    period = year_month or datetime.now(timezone.utc).strftime("%Y-%m")
    employee_code = employee.employee_code
    # ⚠️ 这里原来还预置了 base_salary / performance_score / achievement_rate / breakdown
    # 四个变量，但后面真正用的是 fixed_salary、以及响应里直接写死的
    # performance_score=None / achievement_rate=None / breakdown={...} ——
    # 这四个初始值从头到尾没被读过，留着只会让人以为它们参与计算。
    commission_amount = 0.0
    settlement_result = await db.execute(
        select(MonthlyProfitSettlement).where(
            MonthlyProfitSettlement.period_month == period
        )
    )
    settlement = settlement_result.scalar_one_or_none()

    pr = None
    payroll_data_source = "payroll_record"
    if settlement and getattr(settlement, "status", None) == "approved":
        snapshot_result = await db.execute(
            select(MonthlyProfitPayrollSnapshot).where(
                MonthlyProfitPayrollSnapshot.settlement_id
                == getattr(settlement, "id", None),
                MonthlyProfitPayrollSnapshot.employee_code == employee_code,
                MonthlyProfitPayrollSnapshot.snapshot_status == "active",
            )
        )
        snapshot_rows = snapshot_result.scalars().all()
        pr = snapshot_rows[0] if snapshot_rows else None
        if pr is not None:
            payroll_data_source = "payroll_snapshot"

    if pr is None:
        pr_result = await db.execute(
            select(PayrollRecord).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.year_month == period,
            )
        )
        pr = pr_result.scalar_one_or_none()
    if not pr:
        await _log_me_income_access(
            request, current_user_id, period, "payroll_missing", db
        )
        return MyIncomeResponse(
            linked=True,
            period=period,
            total_income=None,
            breakdown=None,
        )

    fixed_salary = float(
        (getattr(pr, "base_salary", 0) or 0) + (getattr(pr, "position_salary", 0) or 0)
    )
    commission_amount = float(getattr(pr, "commission", 0) or 0)
    net_salary = float(getattr(pr, "net_salary", 0) or 0)
    payroll_status = getattr(pr, "status", None) or getattr(pr, "payroll_status", None)
    is_locked = payroll_status in PAYROLL_LOCKED_STATUSES
    latest_calculated_at = None
    is_stale_against_latest_calc = False

    if payroll_data_source == "payroll_record" and is_locked:
        commission_result = await db.execute(
            select(EmployeeCommission.calculated_at).where(
                EmployeeCommission.employee_code == employee_code,
                EmployeeCommission.year_month == period,
            )
        )
        commission_times = [
            row[0] for row in commission_result.all() if row[0] is not None
        ]
        performance_result = await db.execute(
            select(EmployeePerformance.calculated_at).where(
                EmployeePerformance.employee_code == employee_code,
                EmployeePerformance.year_month == period,
            )
        )
        performance_times = [
            row[0] for row in performance_result.all() if row[0] is not None
        ]
        all_times = [*commission_times, *performance_times]
        if all_times:
            latest_dt = max(all_times)
            latest_calculated_at = (
                latest_dt.isoformat()
                if hasattr(latest_dt, "isoformat")
                else str(latest_dt)
            )
            payroll_updated_at = getattr(pr, "updated_at", None) or getattr(
                pr, "created_at", None
            )
            if (
                is_locked
                and payroll_updated_at is not None
                and latest_dt > payroll_updated_at
            ):
                is_stale_against_latest_calc = True

    payroll_breakdown = {
        "base_salary": float(getattr(pr, "base_salary", 0) or 0),
        "position_salary": float(getattr(pr, "position_salary", 0) or 0),
        "performance_salary": float(getattr(pr, "performance_salary", 0) or 0),
        "overtime_pay": float(getattr(pr, "overtime_pay", 0) or 0),
        "commission": commission_amount,
        "allowances": float(getattr(pr, "allowances", 0) or 0),
        "bonus": float(getattr(pr, "bonus", 0) or 0),
        "gross_salary": float(getattr(pr, "gross_salary", 0) or 0),
        "social_insurance_personal": float(
            getattr(pr, "social_insurance_personal", 0) or 0
        ),
        "housing_fund_personal": float(getattr(pr, "housing_fund_personal", 0) or 0),
        "income_tax": float(getattr(pr, "income_tax", 0) or 0),
        "other_deductions": float(getattr(pr, "other_deductions", 0) or 0),
        "total_deductions": float(getattr(pr, "total_deductions", 0) or 0),
        "net_salary": net_salary,
        "social_insurance_company": float(
            getattr(pr, "social_insurance_company", 0) or 0
        ),
        "housing_fund_company": float(getattr(pr, "housing_fund_company", 0) or 0),
        "total_cost": float(getattr(pr, "total_cost", 0) or 0),
        "status": payroll_status,
        "pay_date": (
            getattr(pr, "pay_date", None).isoformat()
            if getattr(pr, "pay_date", None)
            else None
        ),
        "remark": getattr(pr, "remark", None),
        "data_source": payroll_data_source,
        "is_locked": is_locked,
        "is_stale_against_latest_calc": is_stale_against_latest_calc,
        "latest_calculated_at": latest_calculated_at,
    }
    await _log_me_income_access(request, current_user_id, period, "success", db)
    return MyIncomeResponse(
        linked=True,
        period=period,
        base_salary=fixed_salary,
        commission_amount=commission_amount,
        performance_score=None,
        achievement_rate=None,
        total_income=net_salary,
        breakdown={"payroll": payroll_breakdown},
    )


hr_income_service_dep = provide_service(HRIncomeCalculationService)


async def _build_employee_income_audit(
    *,
    employee_code: str,
    year_month: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    employee = (
        await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
    ).scalar_one_or_none()
    if not employee:
        return error_response(
            ErrorCode.DATA_NOT_FOUND, f"员工不存在: {employee_code}", status_code=404
        )

    settlement = (
        await db.execute(
            select(MonthlyProfitSettlement).where(
                MonthlyProfitSettlement.period_month == year_month
            )
        )
    ).scalar_one_or_none()

    plan = (
        await db.execute(
            select(PersonalPerformancePlan).where(
                PersonalPerformancePlan.year_month == year_month
            )
        )
    ).scalar_one_or_none()
    if (
        plan is not None
        and getattr(plan, "calculation_mode", None) == "controlled_targets_v1"
        and getattr(plan, "scope_confirmed_at", None) is not None
    ):
        scope = (
            await db.execute(
                select(PersonalPerformanceEmployeeScope).where(
                    PersonalPerformanceEmployeeScope.plan_id == plan.id,
                    PersonalPerformanceEmployeeScope.employee_code == employee_code,
                )
            )
        ).scalar_one_or_none()
        snapshots = (
            (
                await db.execute(
                    select(PersonalPerformanceAssignmentSnapshot).where(
                        PersonalPerformanceAssignmentSnapshot.scope_id == scope.id
                    )
                )
            )
            .scalars()
            .all()
            if scope is not None and bool(getattr(scope, "is_included", False))
            else []
        )
        assignments = [
            SimpleNamespace(
                platform_code=snapshot.platform_code,
                shop_id=snapshot.shop_id,
                commission_ratio=snapshot.assignment_ratio_snapshot,
                role=snapshot.role_snapshot,
                sales_target_amount=snapshot.sales_target_amount_snapshot,
            )
            for snapshot in snapshots
        ]
    else:
        assignments = (
            (
                await db.execute(
                    select(EmployeeShopAssignment).where(
                        EmployeeShopAssignment.employee_code == employee_code,
                        EmployeeShopAssignment.year_month == year_month,
                        EmployeeShopAssignment.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )

    shop_rows = []
    for assignment in assignments:
        platform_code = getattr(assignment, "platform_code", None)
        shop_id = getattr(assignment, "shop_id", None)
        alloc_cfg = (
            await db.execute(
                select(ShopCommissionConfig).where(
                    ShopCommissionConfig.year_month == year_month,
                    ShopCommissionConfig.platform_code == platform_code,
                    ShopCommissionConfig.shop_id == shop_id,
                )
            )
        ).scalar_one_or_none()
        perf = (
            await db.execute(
                select(PerformanceScore).where(
                    PerformanceScore.period == year_month,
                    PerformanceScore.platform_code == platform_code,
                    PerformanceScore.shop_id == shop_id,
                )
            )
        ).scalar_one_or_none()
        profit_basis_rows = (
            (
                await db.execute(
                    select(ShopProfitBasis)
                    .where(
                        ShopProfitBasis.period_month == year_month,
                        ShopProfitBasis.platform_code == platform_code,
                        ShopProfitBasis.shop_id == shop_id,
                    )
                    .order_by(ShopProfitBasis.id.desc())
                )
            )
            .scalars()
            .all()
        )
        # 口径已收敛成一套，这里按「结算基数口径优先」取那一条，
        # 不能再按具体版本字符串硬查（历史快照可能留的是旧版本号）。
        profit_basis = next(
            (
                row
                for row in profit_basis_rows
                if not LaborCostPolicyService.is_legacy_a_only_basis_version(
                    getattr(row, "basis_version", "")
                )
            ),
            profit_basis_rows[0] if profit_basis_rows else None,
        )
        shop_rows.append(
            {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "commission_ratio": float(
                    getattr(assignment, "commission_ratio", 0) or 0
                ),
                "role": getattr(assignment, "role", None),
                "sales_target_amount": (
                    float(getattr(assignment, "sales_target_amount", 0) or 0)
                    if getattr(assignment, "sales_target_amount", None) is not None
                    else None
                ),
                "allocatable_profit_rate": (
                    float(getattr(alloc_cfg, "allocatable_profit_rate", 0) or 0)
                    if alloc_cfg
                    else None
                ),
                "profit_basis_amount": (
                    float(getattr(profit_basis, "profit_basis_amount", 0) or 0)
                    if profit_basis
                    else None
                ),
                "shop_performance_score": (
                    float(getattr(perf, "total_score", 0) or 0) if perf else None
                ),
                "shop_performance_coefficient": (
                    float(getattr(perf, "performance_coefficient", 0) or 0)
                    if perf
                    else None
                ),
                "shop_performance_status": (
                    (
                        (getattr(perf, "score_details", None) or {}).get("summary")
                        or {}
                    ).get("status")
                    if perf
                    else None
                ),
                "shop_performance_ready_dimensions": (
                    (
                        (getattr(perf, "score_details", None) or {}).get("summary")
                        or {}
                    ).get("ready_dimensions")
                    if perf
                    else None
                ),
                "shop_performance_pending_dimensions": (
                    (
                        (getattr(perf, "score_details", None) or {}).get("summary")
                        or {}
                    ).get("pending_dimensions")
                    if perf
                    else None
                ),
            }
        )

    perf_inputs = (
        (
            await db.execute(
                select(EmployeePerformanceInput).where(
                    EmployeePerformanceInput.employee_code == employee_code,
                    EmployeePerformanceInput.year_month == year_month,
                    EmployeePerformanceInput.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    adjustments = (
        (
            await db.execute(
                select(EmployeePerformanceAdjustment).where(
                    EmployeePerformanceAdjustment.employee_code == employee_code,
                    EmployeePerformanceAdjustment.year_month == year_month,
                    EmployeePerformanceAdjustment.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    employee_performance = (
        await db.execute(
            select(EmployeePerformance).where(
                EmployeePerformance.employee_code == employee_code,
                EmployeePerformance.year_month == year_month,
            )
        )
    ).scalar_one_or_none()
    employee_commission = (
        await db.execute(
            select(EmployeeCommission).where(
                EmployeeCommission.employee_code == employee_code,
                EmployeeCommission.year_month == year_month,
            )
        )
    ).scalar_one_or_none()
    payroll = (
        await db.execute(
            select(PayrollRecord).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.year_month == year_month,
            )
        )
    ).scalar_one_or_none()

    my_income_like = None
    if payroll:
        payroll_status = getattr(payroll, "status", None)
        is_locked = payroll_status in PAYROLL_LOCKED_STATUSES
        latest_calc_times = []
        if employee_commission and getattr(employee_commission, "calculated_at", None):
            latest_calc_times.append(getattr(employee_commission, "calculated_at"))
        if employee_performance and getattr(
            employee_performance, "calculated_at", None
        ):
            latest_calc_times.append(getattr(employee_performance, "calculated_at"))
        latest_dt = max(latest_calc_times) if latest_calc_times else None
        payroll_updated_at = getattr(payroll, "updated_at", None) or getattr(
            payroll, "created_at", None
        )
        my_income_like = {
            "fixed_salary": float(
                (getattr(payroll, "base_salary", 0) or 0)
                + (getattr(payroll, "position_salary", 0) or 0)
            ),
            "performance_salary": float(getattr(payroll, "performance_salary", 0) or 0),
            "commission": float(getattr(payroll, "commission", 0) or 0),
            "net_salary": float(getattr(payroll, "net_salary", 0) or 0),
            "payroll_status": payroll_status,
            "is_locked": is_locked,
            "is_stale_against_latest_calc": bool(
                is_locked
                and latest_dt
                and payroll_updated_at
                and latest_dt > payroll_updated_at
            ),
            "latest_calculated_at": latest_dt.isoformat() if latest_dt else None,
            "data_source": (
                "payroll_snapshot"
                if settlement and getattr(settlement, "status", None) == "approved"
                else "payroll_record"
            ),
        }

    return {
        "success": True,
        "data": {
            "employee": {
                "employee_code": employee.employee_code,
                "name": getattr(employee, "name", None),
                "user_id": getattr(employee, "user_id", None),
                "position_id": getattr(employee, "position_id", None),
                "department_id": getattr(employee, "department_id", None),
                "status": getattr(employee, "status", None),
                "employee_identity_type": getattr(
                    employee, "employee_identity_type", None
                ),
            },
            "year_month": year_month,
            "settlement_status": (
                getattr(settlement, "status", None) if settlement else None
            ),
            "my_income_projection": my_income_like,
            "shop_assignments": shop_rows,
            "performance_inputs": _audit_performance_inputs(
                legacy_rows=perf_inputs,
                employee_performance=employee_performance,
            ),
            "performance_adjustments": [
                {
                    "adjustment_type": row.adjustment_type,
                    "score_delta": float(row.score_delta or 0),
                    "source": row.source,
                    "reason": row.reason,
                }
                for row in adjustments
            ],
            "employee_performance": (
                _display_employee_performance(employee_performance)
                if employee_performance
                else None
            ),
            "employee_commission": (
                {
                    "sales_amount": float(
                        getattr(employee_commission, "sales_amount", 0) or 0
                    ),
                    "commission_rate": float(
                        getattr(employee_commission, "commission_rate", 0) or 0
                    ),
                    "commission_amount": float(
                        getattr(employee_commission, "commission_amount", 0) or 0
                    ),
                    "calculated_at": (
                        getattr(employee_commission, "calculated_at", None).isoformat()
                        if getattr(employee_commission, "calculated_at", None)
                        else None
                    ),
                }
                if employee_commission
                else None
            ),
            "payroll_record": (
                {
                    "id": getattr(payroll, "id", None),
                    "base_salary": float(getattr(payroll, "base_salary", 0) or 0),
                    "position_salary": float(
                        getattr(payroll, "position_salary", 0) or 0
                    ),
                    "performance_salary": float(
                        getattr(payroll, "performance_salary", 0) or 0
                    ),
                    "commission": float(getattr(payroll, "commission", 0) or 0),
                    "allowances": float(getattr(payroll, "allowances", 0) or 0),
                    "bonus": float(getattr(payroll, "bonus", 0) or 0),
                    "overtime_pay": float(getattr(payroll, "overtime_pay", 0) or 0),
                    "gross_salary": float(getattr(payroll, "gross_salary", 0) or 0),
                    "total_deductions": float(
                        getattr(payroll, "total_deductions", 0) or 0
                    ),
                    "net_salary": float(getattr(payroll, "net_salary", 0) or 0),
                    "total_cost": float(getattr(payroll, "total_cost", 0) or 0),
                    "status": getattr(payroll, "status", None),
                    "updated_at": (
                        getattr(payroll, "updated_at", None).isoformat()
                        if getattr(payroll, "updated_at", None)
                        else None
                    ),
                }
                if payroll
                else None
            ),
        },
    }


@router.post("/income/calculate", response_model=IncomeCalculationResponse)
async def calculate_income_c_class(
    year_month: str = Query(..., description="月份(YYYY-MM)"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    service: HRIncomeCalculationService = Depends(hr_income_service_dep),
):
    """重算员工收入 C 类表（employee_commissions / employee_performance）。"""
    try:
        result = await service.calculate_month(year_month)
        return IncomeCalculationResponse(**result)
    except ValueError as e:
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            f"参数错误: {str(e)}",
            status_code=400,
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"重算员工收入C类数据失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"重算员工收入C类数据失败: {str(e)}",
            status_code=500,
        )


@router.get("/income-audit/{employee_code}/{year_month}")
async def get_employee_income_audit(
    employee_code: str,
    year_month: str,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    if not is_admin_user(current_user):
        return error_response(
            ErrorCode.PERMISSION_DENIED,
            "需要管理员权限才能查看员工收入审计视图",
            status_code=403,
        )
    try:
        return await _build_employee_income_audit(
            employee_code=employee_code,
            year_month=year_month,
            db=db,
        )
    except Exception as e:
        logger.error(f"获取员工收入审计视图失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"获取员工收入审计视图失败: {str(e)}",
            status_code=500,
        )


@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    position_id: Optional[int] = Query(None, description="职位ID筛选"),
    status: Optional[str] = Query(
        None, description="状态筛选(active/inactive/probation/leave)"
    ),
    identity_type: Optional[str] = Query(
        None, description="用工身份筛选(employee/visitor)，不传=全部"
    ),
    keyword: Optional[str] = Query(None, description="关键字搜索(姓名/工号)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=500, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取员工列表(分页、筛选)"""
    try:
        identity_type = _validated_identity_filter(identity_type)
    except ValueError as e:
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
        )
    try:
        query = select(
            Employee, Position.position_code, Position.position_name
        ).outerjoin(
            Position,
            Employee.position_id == Position.id,
        )
        conditions = []

        if department_id is not None:
            conditions.append(Employee.department_id == department_id)
        if position_id is not None:
            conditions.append(Employee.position_id == position_id)
        if status:
            conditions.append(Employee.status == status)
        if identity_type:
            conditions.append(Employee.employee_identity_type == identity_type)
        if keyword:
            conditions.append(
                or_(
                    Employee.name.ilike(f"%{keyword}%"),
                    Employee.employee_code.ilike(f"%{keyword}%"),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        offset = (page - 1) * page_size
        query = query.order_by(Employee.employee_code).offset(offset).limit(page_size)

        result = await db.execute(query)
        employee_rows = result.all()
        # 部门名一次批量取（不逐行查）
        department_names = await _department_name_map(
            db, [getattr(emp, "department_id", None) for emp, _, _ in employee_rows]
        )
        out = []
        for emp, position_code, position_name in employee_rows:
            resp = EmployeeResponse.model_validate(emp)
            resp = resp.model_copy(
                update={
                    "username": await _username_for_user_id(db, emp.user_id),
                    "position_code": position_code,
                    "position_name": position_name,
                    "department_name": department_names.get(
                        getattr(emp, "department_id", None)
                    ),
                }
            )
            out.append(resp)
        return out
    except Exception as e:
        logger.error(f"获取员工列表失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"获取员工列表失败: {str(e)}",
            status_code=500,
        )


@router.get("/employees/count")
async def count_employees(
    status: Optional[str] = Query(None, description="状态筛选"),
    identity_type: Optional[str] = Query(
        None, description="用工身份筛选(employee/visitor)，不传=全部"
    ),
    db: AsyncSession = Depends(get_async_db),
):
    """获取员工总数（用于人效计算等）"""
    try:
        identity_type = _validated_identity_filter(identity_type)
    except ValueError as e:
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            str(e),
            status_code=400,
        )
    try:
        query = select(func.count(Employee.id))

        if status:
            query = query.where(Employee.status == status)
        if identity_type:
            query = query.where(Employee.employee_identity_type == identity_type)

        result = await db.execute(query)
        count = result.scalar()

        return {"count": count, "status": status or "all"}
    except Exception as e:
        logger.error(f"获取员工总数失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"获取员工总数失败: {str(e)}",
            status_code=500,
        )


@router.get("/employees/{employee_code}", response_model=EmployeeResponse)
async def get_employee(employee_code: str, db: AsyncSession = Depends(get_async_db)):
    """获取员工详情"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        username = await _username_for_user_id(db, employee.user_id)
        department_names = await _department_name_map(
            db, [getattr(employee, "department_id", None)]
        )
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(
            update={
                "username": username,
                "department_name": department_names.get(
                    getattr(employee, "department_id", None)
                ),
            }
        )
    except Exception as e:
        logger.error(f"获取员工详情失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"获取员工详情失败: {str(e)}",
            status_code=500,
        )


async def _generate_employee_code(db: AsyncSession) -> str:
    """生成员工编号：EMP + 年份后2位 + 4位流水号，如 EMP260001"""
    year_suffix = datetime.now().strftime("%y")
    prefix = f"EMP{year_suffix}"
    result = await db.execute(
        select(Employee.employee_code).where(Employee.employee_code.like(f"{prefix}%"))
    )
    rows = result.scalars().all()
    max_seq = 0
    for code in rows:
        try:
            seq = int(code[len(prefix) :]) if len(code) > len(prefix) else 0
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate, db: AsyncSession = Depends(get_async_db)
):
    """创建员工；员工编号不传或为空时自动生成"""
    try:
        data = employee.model_dump()
        employee_code = data.get("employee_code") or None
        if not employee_code or not str(employee_code).strip():
            employee_code = await _generate_employee_code(db)
            data["employee_code"] = employee_code

        existing = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        if existing.scalar_one_or_none():
            return error_response(
                ErrorCode.DATA_ALREADY_EXISTS,
                f"员工编号已存在: {employee_code}",
                status_code=400,
            )
        user_id = data.get("user_id")
        if user_id is not None:
            other = await db.execute(
                select(Employee).where(Employee.user_id == user_id)
            )
            if other.scalar_one_or_none():
                return error_response(
                    ErrorCode.DATA_ALREADY_EXISTS,
                    "该登录账号已关联其他员工",
                    status_code=400,
                )
        new_employee = Employee(**data)
        db.add(new_employee)
        await db.commit()
        await db.refresh(new_employee)
        logger.info(f"创建员工成功: {new_employee.employee_code} - {new_employee.name}")
        username = await _username_for_user_id(db, new_employee.user_id)
        resp = EmployeeResponse.model_validate(new_employee)
        return resp.model_copy(update={"username": username})
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR, f"创建员工失败: {str(e)}", status_code=500
        )


@router.put("/employees/{employee_code}", response_model=EmployeeResponse)
async def update_employee(
    employee_code: str,
    employee_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    """更新员工信息"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        update_data = employee_update.model_dump(exclude_unset=True)
        if "user_id" in update_data and update_data["user_id"] is not None:
            other = await db.execute(
                select(Employee).where(
                    Employee.user_id == update_data["user_id"],
                    Employee.id != employee.id,
                )
            )
            if other.scalar_one_or_none():
                return error_response(
                    ErrorCode.DATA_ALREADY_EXISTS,
                    "该登录账号已关联其他员工",
                    status_code=400,
                )
        for key, value in update_data.items():
            setattr(employee, key, value)
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(employee)
        logger.info(f"更新员工成功: {employee_code}")
        username = await _username_for_user_id(db, employee.user_id)
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(update={"username": username})
    except Exception as e:
        await db.rollback()
        logger.error(f"更新员工失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR, f"更新员工失败: {str(e)}", status_code=500
        )


@router.delete("/employees/{employee_code}", status_code=204)
async def delete_employee(employee_code: str, db: AsyncSession = Depends(get_async_db)):
    """删除员工(软删除:设置status为inactive)。

    ⚠️ **本端点是 legacy 路径**。新的离职流程请用
    ``POST /api/hr/employees/{employee_code}/offboard`` —— 只有它才会
    写离职日期、最后发薪月、解除账号关联、失效未来归属。

    守卫改造（2026-11-20）：旧守卫是「该员工**有任何**归属记录就拦」
    （不分月份、不分状态）⇒ 历史归属永远删不掉员工。
    现在**只拦「当前月之后仍有 ``status='active'`` 的归属」** ——
    历史归属不再阻断（历史归属要保留给审计与往月重算）。
    """
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        assign_result = await db.execute(
            select(EmployeeShopAssignment).where(
                EmployeeShopAssignment.employee_code == employee_code,
                EmployeeShopAssignment.year_month > current_month,
                EmployeeShopAssignment.status == "active",
            )
        )
        if assign_result.scalars().first():
            return error_response(
                ErrorCode.DATA_INTEGRITY_VIOLATION,
                "该员工在当前月之后仍有生效中的店铺归属，请先解除未来的归属"
                "（或改用 POST /api/hr/employees/{employee_code}/offboard 办理离职）",
                status_code=400,
            )
        employee.status = "inactive"
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"删除员工成功(软删除): {employee_code}")
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"删除员工失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR, f"删除员工失败: {str(e)}", status_code=500
        )


# ============================================================================
# 员工生命周期端点（离职 / 转正 / 访客转正 / 访客合并）
# ============================================================================


@router.post(
    "/employees/{employee_code}/offboard", response_model=EmployeeOffboardResponse
)
async def offboard_employee(
    employee_code: str,
    body: EmployeeOffboardRequest,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """办理离职：一次事务完成「置离职 + 解除账号关联 + 失效未来归属」。

    * ``status = 'inactive'``，写 ``leave_date`` / ``last_payroll_month`` /
      ``leave_reason`` / ``updated_at``
    * **解除账号关联**：``user_id`` 置空 ⇒ 账号归还账号池（离职员工不该还能登录）
    * **失效未来归属**：``a_class.employee_shop_assignments`` 中
      ``year_month > last_payroll_month`` 且 ``status='active'`` 的行置为
      ``inactive``（**只改状态、不删行** —— 归属行是往月重算与审计的依据）
    * 记一条审计日志（resource = ``employee/offboard``）

    ⚠️ **不阻断草稿工资单**：离职当月及之前若还有 ``status='draft'`` 的工资单，
    只在响应里带 ``pending_payroll_months`` 提醒前端（离职结算是生命线，
    不能因为一张草稿单把人卡在职）。
    """
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        # ⚠️ 在职状态判定走 SSOT（backend/services/hr_employee_lifecycle.py），
        #    不允许在这里自己写 ``status == 'inactive'``。
        if employee_status(employee) == "inactive":
            return error_response(
                ErrorCode.PARAMETER_INVALID,
                "该员工已是离职状态，不可重复办理离职",
                status_code=400,
            )

        # 待确认的草稿工资单（提醒，不阻断）
        pending_result = await db.execute(
            select(PayrollRecord).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.status == "draft",
                PayrollRecord.year_month <= body.last_payroll_month,
            )
        )
        pending_payroll_months = sorted(
            {row.year_month for row in pending_result.scalars().all()}
        )

        # 1) 员工本体
        employee.status = "inactive"
        employee.leave_date = body.leave_date
        employee.last_payroll_month = body.last_payroll_month
        employee.leave_reason = body.leave_reason
        employee.updated_at = datetime.now(timezone.utc)

        # 2) 解除账号关联（账号归还账号池）
        released_user_id = getattr(employee, "user_id", None)
        released_username = await _username_for_user_id(db, released_user_id)
        employee.user_id = None

        # 3) 失效未来归属（只改状态、不删行，保留审计）
        future_result = await db.execute(
            select(EmployeeShopAssignment).where(
                EmployeeShopAssignment.employee_code == employee_code,
                EmployeeShopAssignment.year_month > body.last_payroll_month,
                EmployeeShopAssignment.status == "active",
            )
        )
        future_assignments = future_result.scalars().all()
        for assignment in future_assignments:
            assignment.status = "inactive"

        # 4) 业务变更一次提交
        await db.commit()
        await db.refresh(employee)

        # 5) 审计（沿用仓库既有模式：业务提交之后再写审计）
        await audit_service.log_action(
            user_id=getattr(current_user, "user_id", None),
            action="offboard",
            resource="employee/offboard",
            resource_id=employee_code,
            ip_address="system",
            user_agent="hr_employee_router",
            details={
                "result_status": "offboarded",
                "employee_code": employee_code,
                "leave_date": body.leave_date.isoformat(),
                "last_payroll_month": body.last_payroll_month,
                "leave_reason": body.leave_reason,
                "released_user_id": released_user_id,
                "released_username": released_username,
                "deactivated_assignments": len(future_assignments),
                "pending_payroll_months": pending_payroll_months,
            },
            db=db,
        )

        resp = EmployeeOffboardResponse.model_validate(employee)
        return resp.model_copy(
            update={"pending_payroll_months": pending_payroll_months}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"办理员工离职失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"办理员工离职失败: {str(e)}",
            status_code=500,
        )


@router.post("/employees/{employee_code}/regularize", response_model=EmployeeResponse)
async def regularize_employee(
    employee_code: str,
    body: EmployeeRegularizeRequest,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """转正：试用期（``probation``）→ 在职（``active``）。

    只有试用期员工可转正；其它状态一律 400（避免把离职员工"转正"回来）。
    """
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        if employee_status(employee) != "probation":
            return error_response(
                ErrorCode.PARAMETER_INVALID,
                f"只有试用期员工可转正，当前状态: {employee_status(employee)}",
                status_code=400,
            )

        employee.status = "active"
        employee.regularization_date = body.regularization_date
        if body.probation_end_date is not None:
            employee.probation_end_date = body.probation_end_date
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(employee)

        await audit_service.log_action(
            user_id=getattr(current_user, "user_id", None),
            action="regularize",
            resource="employee/regularize",
            resource_id=employee_code,
            ip_address="system",
            user_agent="hr_employee_router",
            details={
                "result_status": "regularized",
                "employee_code": employee_code,
                "regularization_date": body.regularization_date.isoformat(),
                "probation_end_date": (
                    body.probation_end_date.isoformat()
                    if body.probation_end_date
                    else None
                ),
            },
            db=db,
        )

        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(
            update={"username": await _username_for_user_id(db, employee.user_id)}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"员工转正失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"员工转正失败: {str(e)}",
            status_code=500,
        )


@router.post(
    "/employees/{employee_code}/promote-visitor", response_model=EmployeeResponse
)
async def promote_visitor_employee(
    employee_code: str,
    body: EmployeeVisitorPromotionRequest,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """访客转正：``employee_identity_type`` 由 ``visitor`` 改为 ``employee``。

    可选地补 ``hire_date`` / ``department_id`` / ``position_id``。
    """
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"员工不存在: {employee_code}",
                status_code=404,
            )
        # ⚠️ 用工身份判定走 SSOT
        if employee_identity(employee) != "visitor":
            return error_response(
                ErrorCode.PARAMETER_INVALID,
                f"只有访客档案可转正，当前用工身份: {employee_identity(employee)}",
                status_code=400,
            )

        employee.employee_identity_type = body.employee_identity_type
        if body.hire_date is not None:
            employee.hire_date = body.hire_date
        if body.department_id is not None:
            employee.department_id = body.department_id
        if body.position_id is not None:
            employee.position_id = body.position_id
        employee.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(employee)

        await audit_service.log_action(
            user_id=getattr(current_user, "user_id", None),
            action="promote_visitor",
            resource="employee/promote-visitor",
            resource_id=employee_code,
            ip_address="system",
            user_agent="hr_employee_router",
            details={
                "result_status": "promoted",
                "employee_code": employee_code,
                "employee_identity_type": body.employee_identity_type,
                "department_id": body.department_id,
                "position_id": body.position_id,
                "hire_date": body.hire_date.isoformat() if body.hire_date else None,
            },
            db=db,
        )

        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(
            update={"username": await _username_for_user_id(db, employee.user_id)}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"访客转正失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"访客转正失败: {str(e)}",
            status_code=500,
        )


@router.post(
    "/employees/{employee_code}/merge-visitor", response_model=EmployeeResponse
)
async def merge_visitor_employee(
    employee_code: str,
    body: EmployeeMergeRequest,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """合并访客档案：把访客（``source``）并进正式员工（``target``）。

    一次事务完成：

    * 联系方式（``phone`` / ``email`` / ``address`` / ``emergency_contact`` /
      ``emergency_phone``）**仅当 target 对应字段为空时**才搬（不覆盖已有值）
    * target 没有 ``user_id`` 而 source 有 ⇒ 把 ``user_id`` 搬过去
    * **删除 source 这条员工档案**（真删 —— 它是访客副产品，不是业务记录）
    * 记审计日志
    """
    try:
        source_code = body.source_employee_code.strip()
        if source_code == employee_code:
            return error_response(
                ErrorCode.PARAMETER_INVALID,
                "源访客档案与目标员工不能是同一条记录",
                status_code=400,
            )

        target_result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        target = target_result.scalar_one_or_none()
        if not target:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"目标员工不存在: {employee_code}",
                status_code=404,
            )

        source_result = await db.execute(
            select(Employee).where(Employee.employee_code == source_code)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                f"源访客档案不存在: {source_code}",
                status_code=404,
            )
        # ⚠️ 用工身份判定走 SSOT
        if employee_identity(source) != "visitor":
            return error_response(
                ErrorCode.PARAMETER_INVALID,
                f"只有访客档案可以被合并，{source_code} 的用工身份为 "
                f"{employee_identity(source)}",
                status_code=400,
            )

        # 源账号不能已被别的员工占用（否则把 user_id 搬过去会造成一号两人）
        source_user_id = getattr(source, "user_id", None)
        released_user_id = None
        if source_user_id:
            occupied_result = await db.execute(
                select(Employee).where(
                    Employee.user_id == source_user_id,
                    Employee.id != source.id,
                )
            )
            for occupied in occupied_result.scalars().all():
                if occupied.id == target.id:
                    continue
                return error_response(
                    ErrorCode.DATA_ALREADY_EXISTS,
                    f"访客 {source_code} 绑定的账号已被员工 "
                    f"{occupied.employee_code} 占用，无法合并",
                    status_code=400,
                )
            released_user_id = source_user_id

        # 1) 联系方式：仅当 target 对应字段为空时才搬
        moved_fields = _merge_employee_contact_fields(target, source)

        # 2) 账号：target 没有才搬
        if getattr(target, "user_id", None) is None and released_user_id is not None:
            target.user_id = released_user_id
            moved_fields = moved_fields + ["user_id"]

        target.updated_at = datetime.now(timezone.utc)

        # 3) 删除访客档案（真删）
        await db.delete(source)

        await db.commit()
        await db.refresh(target)

        await audit_service.log_action(
            user_id=getattr(current_user, "user_id", None),
            action="merge_visitor",
            resource="employee/merge-visitor",
            resource_id=employee_code,
            ip_address="system",
            user_agent="hr_employee_router",
            details={
                "result_status": "merged",
                "target_employee_code": employee_code,
                "source_employee_code": source_code,
                "moved_fields": moved_fields,
            },
            db=db,
        )

        resp = EmployeeResponse.model_validate(target)
        return resp.model_copy(
            update={"username": await _username_for_user_id(db, target.user_id)}
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"合并访客档案失败: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"合并访客档案失败: {str(e)}",
            status_code=500,
        )


# ============================================================================
# 排班班次API
