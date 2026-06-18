from __future__ import annotations

"""
HR - 薪资与目标管理
"""

from datetime import date
import inspect
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user, is_admin_user
from backend.models.database import get_async_db
from backend.schemas.hr import (
    EmployeeTargetCreate,
    EmployeeTargetResponse,
    EmployeeTargetUpdate,
    PayrollRecordManualUpdate,
    PayrollRecordResponse,
    SalaryStructureCreate,
    SalaryStructureUpdate,
    SalaryStructureResponse,
)
from backend.services.audit_service import audit_service
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.payroll_generation_service import PayrollGenerationService
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.db import DimUser, Employee, EmployeeTarget, PayrollRecord, SalaryStructure
from modules.core.db import EmployeeCommission, EmployeePerformance
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR-薪资目标"])


def _payroll_success(record: PayrollRecord) -> Dict[str, Any]:
    return {
        "success": True,
        "data": PayrollRecordResponse.model_validate(record).model_dump(mode="json"),
    }


async def _compute_payroll_stale_flags(
    *,
    db: AsyncSession,
    record: Any | None,
) -> Dict[str, Any]:
    if record is None:
        return {
            "is_locked": False,
            "is_stale_against_latest_calc": False,
            "latest_calculated_at": None,
        }

    payroll_status = getattr(record, "status", None)
    is_locked = payroll_status in {"confirmed", "paid", "approved"}
    if not is_locked:
        return {
            "is_locked": False,
            "is_stale_against_latest_calc": False,
            "latest_calculated_at": None,
        }

    employee_code = getattr(record, "employee_code", None)
    year_month = getattr(record, "year_month", None)
    if not employee_code or not year_month:
        return {
            "is_locked": True,
            "is_stale_against_latest_calc": False,
            "latest_calculated_at": None,
        }

    commission_result = await db.execute(
        select(EmployeeCommission.calculated_at).where(
            EmployeeCommission.employee_code == employee_code,
            EmployeeCommission.year_month == year_month,
        )
    )
    commission_times = [row[0] for row in commission_result.all() if row[0] is not None]
    performance_result = await db.execute(
        select(EmployeePerformance.calculated_at).where(
            EmployeePerformance.employee_code == employee_code,
            EmployeePerformance.year_month == year_month,
        )
    )
    performance_times = [row[0] for row in performance_result.all() if row[0] is not None]
    all_times = [*commission_times, *performance_times]
    latest_dt = max(all_times) if all_times else None
    payroll_updated_at = getattr(record, "updated_at", None) or getattr(record, "created_at", None)
    return {
        "is_locked": True,
        "is_stale_against_latest_calc": bool(latest_dt and payroll_updated_at and latest_dt > payroll_updated_at),
        "latest_calculated_at": latest_dt.isoformat() if latest_dt else None,
    }


def _employee_identity_allows_salary(employee: Employee | None) -> bool:
    if employee is None:
        return True
    status = getattr(employee, "status", "active")
    identity = getattr(employee, "employee_identity_type", "employee")
    return (
        status == "active"
        and identity == "employee"
    )


def _extract_optional_employee(result: Any) -> Employee | None:
    scalar_getter = getattr(result, "scalar_one_or_none", None)
    if callable(scalar_getter) and not inspect.iscoroutinefunction(scalar_getter):
        employee = scalar_getter()
        if not inspect.isawaitable(employee) and employee is not None and hasattr(employee, "employee_code"):
            return employee

    scalars_getter = getattr(result, "scalars", None)
    if callable(scalars_getter) and not inspect.iscoroutinefunction(scalars_getter):
        scalar_rows = scalars_getter()
        all_getter = getattr(scalar_rows, "all", None)
        if callable(all_getter) and not inspect.iscoroutinefunction(all_getter):
            rows = all_getter()
            if rows:
                employee = rows[0]
                if hasattr(employee, "employee_code"):
                    return employee

    return None


def _salary_identity_rejection():
    return error_response(
        ErrorCode.PARAMETER_INVALID,
        "当前员工身份不允许进入薪资链路",
        status_code=409,
    )


async def _load_salary_structure_versions(
    db: AsyncSession,
    employee_code: str,
) -> List[SalaryStructure]:
    result = await db.execute(
        select(SalaryStructure)
        .where(SalaryStructure.employee_code == employee_code)
        .order_by(desc(SalaryStructure.effective_date), desc(SalaryStructure.id))
    )
    return result.scalars().all()


def _pick_current_salary_structure(rows: List[SalaryStructure]) -> Optional[SalaryStructure]:
    if not rows:
        return None
    today = date.today()
    active_current_rows = [
        row
        for row in rows
        if getattr(row, "status", None) == "active"
        and getattr(row, "effective_date", None) is not None
        and row.effective_date <= today
    ]
    if active_current_rows:
        return active_current_rows[0]
    active_rows = [row for row in rows if getattr(row, "status", None) == "active"]
    if active_rows:
        return active_rows[0]
    return rows[0]


@router.get("/salary-structures", response_model=List[SalaryStructureResponse])
async def list_salary_structures(
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        query = select(SalaryStructure)
        if status:
            query = query.where(SalaryStructure.status == status)
        query = query.order_by(SalaryStructure.employee_code).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return [SalaryStructureResponse.model_validate(row) for row in result.scalars().all()]
    except Exception as e:
        logger.error("获取薪资结构列表失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取薪资结构列表失败: {str(e)}", status_code=500)


@router.get("/salary-structures/{employee_code}", response_model=SalaryStructureResponse)
async def get_salary_structure(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        rows = await _load_salary_structure_versions(db, employee_code)
        structure = _pick_current_salary_structure(rows)
        if not structure:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"薪资结构不存在: {employee_code}", status_code=404)
        return SalaryStructureResponse.model_validate(structure)
    except Exception as e:
        logger.error("获取薪资结构失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取薪资结构失败: {str(e)}", status_code=500)


@router.get("/salary-structures/{employee_code}/history", response_model=List[SalaryStructureResponse])
async def list_salary_structure_history(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        rows = await _load_salary_structure_versions(db, employee_code)
        return [SalaryStructureResponse.model_validate(row) for row in rows]
    except Exception as e:
        logger.error("鑾峰彇钖祫缁撴瀯鍘嗗彶澶辫触: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"鑾峰彇钖祫缁撴瀯鍘嗗彶澶辫触: {str(e)}", status_code=500)


@router.post("/salary-structures", response_model=SalaryStructureResponse, status_code=201)
async def create_salary_structure(
    structure: SalaryStructureCreate,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == structure.employee_code)
        )
        employee = _extract_optional_employee(employee)
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {structure.employee_code}", status_code=400)

        if not _employee_identity_allows_salary(employee):
            return _salary_identity_rejection()

        existing = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_code == structure.employee_code,
                    SalaryStructure.effective_date == structure.effective_date,
                )
            )
        )
        if existing.scalar_one_or_none():
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"薪资结构已存在: {structure.employee_code}", status_code=400)

        record = SalaryStructure(**structure.model_dump())
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return SalaryStructureResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error("创建薪资结构失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建薪资结构失败: {str(e)}", status_code=500)


@router.put("/salary-structures/{employee_code}", response_model=SalaryStructureResponse)
async def update_salary_structure(
    employee_code: str,
    body: SalaryStructureUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = _extract_optional_employee(employee)
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"鍛樺伐涓嶅瓨鍦? {employee_code}", status_code=404)
        if not _employee_identity_allows_salary(employee):
            return _salary_identity_rejection()

        rows = await _load_salary_structure_versions(db, employee_code)
        record = _pick_current_salary_structure(rows)
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"钖祫缁撴瀯涓嶅瓨鍦? {employee_code}", status_code=404)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
        await db.commit()
        await db.refresh(record)
        return SalaryStructureResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error("鏇存柊钖祫缁撴瀯澶辫触: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"鏇存柊钖祫缁撴瀯澶辫触: {str(e)}", status_code=500)


@router.post("/payroll-records/{employee_code}/{year_month}/refresh")
async def refresh_payroll_record(
    employee_code: str,
    year_month: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = _extract_optional_employee(employee)
        if employee is None:
            employee = SimpleNamespace(employee_code=employee_code, status="active", employee_identity_type="employee")
        if not employee:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"鍛樺伐涓嶅瓨鍦? {employee_code}", status_code=404)
        if not _employee_identity_allows_salary(employee):
            return _salary_identity_rejection()

        await HRIncomeCalculationService(db).calculate_month(year_month, commit=False)
        result = await PayrollGenerationService(db).generate_employee_month(employee_code, year_month)
        record = result.get("payroll_record")
        if record is not None and result.get("payroll_upserts", 0) > 0:
            await db.commit()
            await db.refresh(record)
        stale_flags = await _compute_payroll_stale_flags(db=db, record=record)
        return {
            "success": True,
            "employee_code": result.get("employee_code", employee_code),
            "year_month": result.get("year_month", year_month),
            "payroll_upserts": result.get("payroll_upserts", 0),
            "locked_conflicts": result.get("locked_conflicts", 0),
            "locked_conflict_details": result.get("locked_conflict_details", []),
            "is_locked": stale_flags["is_locked"],
            "is_stale_against_latest_calc": stale_flags["is_stale_against_latest_calc"],
            "latest_calculated_at": stale_flags["latest_calculated_at"],
            "data": PayrollRecordResponse.model_validate(record).model_dump(mode="json") if record else None,
        }
    except Exception as e:
        logger.error("鍒锋柊鍛樺伐鏈堝害宸ヨ祫鍗曞け璐? %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"鍒锋柊鍛樺伐鏈堝害宸ヨ祫鍗曞け璐? {str(e)}", status_code=500)


@router.post("/payroll-records/{year_month}/refresh-all")
async def refresh_payroll_records_for_month(
    year_month: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        income_result = await HRIncomeCalculationService(db).calculate_month(year_month, commit=False)
        payroll_result = await PayrollGenerationService(db).generate_month(year_month)

        if (
            income_result.get("commission_upserts", 0) > 0
            or income_result.get("performance_upserts", 0) > 0
            or payroll_result.get("payroll_upserts", 0) > 0
        ):
            await db.commit()

        return {
            "success": True,
            "year_month": year_month,
            "commission_upserts": income_result.get("commission_upserts", 0),
            "performance_upserts": income_result.get("performance_upserts", 0),
            "employee_count": payroll_result.get("employee_count", 0),
            "payroll_upserts": payroll_result.get("payroll_upserts", 0),
            "locked_conflicts": payroll_result.get("locked_conflicts", 0),
            "locked_conflict_details": payroll_result.get("locked_conflict_details", []),
        }
    except Exception as e:
        logger.error("鎸夋湀浠芥壒閲忓埛鏂板伐璧勫崟澶辫触: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"鎸夋湀浠芥壒閲忓埛鏂板伐璧勫崟澶辫触: {str(e)}", status_code=500)


@router.get("/payroll-records", response_model=List[PayrollRecordResponse])
async def list_payroll_records(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="工资月份筛选(YYYY-MM)"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        query = select(PayrollRecord)
        conditions = []
        if employee_code:
            conditions.append(PayrollRecord.employee_code == employee_code)
        if year_month:
            conditions.append(PayrollRecord.year_month == year_month)
        if status:
            conditions.append(PayrollRecord.status == status)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(PayrollRecord.year_month.desc(), PayrollRecord.employee_code).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return [PayrollRecordResponse.model_validate(row) for row in result.scalars().all()]
    except Exception as e:
        logger.error("获取工资单列表失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取工资单列表失败: {str(e)}", status_code=500)


@router.get("/payroll-records/{employee_code}/{year_month}")
async def get_payroll_record_detail(
    employee_code: str,
    year_month: str,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await db.execute(
            select(PayrollRecord).where(
                PayrollRecord.employee_code == employee_code,
                PayrollRecord.year_month == year_month,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, "工资单不存在", status_code=404)
        stale_flags = await _compute_payroll_stale_flags(db=db, record=record)
        payload = PayrollRecordResponse.model_validate(record).model_dump(mode="json")
        payload.update(stale_flags)
        return {"success": True, "data": payload}
    except Exception as e:
        logger.error("获取工资单详情失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取工资单详情失败: {str(e)}", status_code=500)


@router.put("/payroll-records/{record_id}")
async def update_payroll_record(
    record_id: int,
    body: PayrollRecordManualUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await db.execute(
            select(PayrollRecord).where(PayrollRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, "工资单不存在", status_code=404)
        if record.status != "draft":
            return error_response(ErrorCode.PARAMETER_INVALID, "非 draft 工资单不允许编辑", status_code=409)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
        PayrollGenerationService.recalculate_record_totals(record)
        await db.commit()
        await db.refresh(record)
        return _payroll_success(record)
    except Exception as e:
        await db.rollback()
        logger.error("更新工资单失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新工资单失败: {str(e)}", status_code=500)


@router.post("/payroll-records/{record_id}/confirm")
async def confirm_payroll_record(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await db.execute(
            select(PayrollRecord).where(PayrollRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, "工资单不存在", status_code=404)
        if record.status == "paid":
            return error_response(ErrorCode.PARAMETER_INVALID, "已发放工资单不可再次确认", status_code=409)
        record.status = "confirmed"
        await db.commit()
        await db.refresh(record)
        return _payroll_success(record)
    except Exception as e:
        await db.rollback()
        logger.error("确认工资单失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"确认工资单失败: {str(e)}", status_code=500)


@router.post("/payroll-records/{record_id}/reopen")
async def reopen_payroll_record(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await db.execute(
            select(PayrollRecord).where(PayrollRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, "工资单不存在", status_code=404)
        if record.status == "paid":
            return error_response(ErrorCode.PARAMETER_INVALID, "已发放工资单不可退回 draft", status_code=409)
        record.status = "draft"
        await db.commit()
        await db.refresh(record)
        return _payroll_success(record)
    except Exception as e:
        await db.rollback()
        logger.error("退回工资单失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"退回工资单失败: {str(e)}", status_code=500)


@router.post("/payroll-records/{record_id}/pay")
async def mark_payroll_record_paid(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(get_current_user),
):
    try:
        if not is_admin_user(current_user):
            return error_response(
                ErrorCode.PERMISSION_DENIED,
                "需要管理员权限才能标记工资单为已发放",
                status_code=403,
            )
        result = await db.execute(
            select(PayrollRecord).where(PayrollRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, "工资单不存在", status_code=404)
        if record.status != "confirmed":
            return error_response(ErrorCode.PARAMETER_INVALID, "仅已确认工资单允许标记为已发放", status_code=409)
        record.status = "paid"
        if not record.pay_date:
            from datetime import date

            record.pay_date = date.today()
        await db.commit()
        await db.refresh(record)
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="pay",
            resource="payroll_record",
            resource_id=str(record_id),
            ip_address="system",
            user_agent="hr_salary_router",
            details={
                "result_status": "paid",
                "employee_code": record.employee_code,
                "year_month": record.year_month,
                "pay_date": record.pay_date.isoformat() if record.pay_date else None,
            },
            db=db,
        )
        return _payroll_success(record)
    except Exception as e:
        await db.rollback()
        logger.error("标记工资单已发放失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"标记工资单已发放失败: {str(e)}", status_code=500)


@router.get("/employee-targets", response_model=List[EmployeeTargetResponse])
async def list_employee_targets(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    target_type: Optional[str] = Query(None, description="目标类型筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=500, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    """个人目标规划层查询接口，不直接参与个人绩效结果和工资单计算。"""
    try:
        query = select(EmployeeTarget)
        conditions = []
        if employee_code:
            conditions.append(EmployeeTarget.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeeTarget.year_month == year_month)
        if target_type:
            conditions.append(EmployeeTarget.target_type == target_type)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(EmployeeTarget.year_month.desc(), EmployeeTarget.employee_code).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return [EmployeeTargetResponse.model_validate(row) for row in result.scalars().all()]
    except Exception as e:
        logger.error("获取员工目标列表失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工目标列表失败: {str(e)}", status_code=500)


@router.post("/employee-targets", response_model=EmployeeTargetResponse, status_code=201)
async def create_employee_target(
    target: EmployeeTargetCreate,
    db: AsyncSession = Depends(get_async_db),
):
    """个人目标规划层创建接口，不直接参与个人绩效结果和工资单计算。"""
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == target.employee_code)
        )
        if not employee.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {target.employee_code}", status_code=400)

        existing = await db.execute(
            select(EmployeeTarget).where(
                and_(
                    EmployeeTarget.employee_code == target.employee_code,
                    EmployeeTarget.year_month == target.year_month,
                    EmployeeTarget.target_type == target.target_type,
                )
            )
        )
        if existing.scalar_one_or_none():
            return error_response(
                ErrorCode.DATA_ALREADY_EXISTS,
                f"员工目标已存在: {target.employee_code} - {target.year_month} - {target.target_type}",
                status_code=400,
            )

        record = EmployeeTarget(**target.model_dump())
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return EmployeeTargetResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error("创建员工目标失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建员工目标失败: {str(e)}", status_code=500)

@router.put("/employee-targets/{target_id}", response_model=EmployeeTargetResponse)
async def update_employee_target(
    target_id: int,
    target: EmployeeTargetUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    """更新个人目标规划层记录，不直接参与个人绩效结果和工资单计算。"""
    try:
        result = await db.execute(select(EmployeeTarget).where(EmployeeTarget.id == target_id))
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工目标不存在: {target_id}", status_code=404)

        update_data = target.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(record, field, value)

        await db.commit()
        await db.refresh(record)
        return EmployeeTargetResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error("更新员工目标失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新员工目标失败: {str(e)}", status_code=500)


@router.delete("/employee-targets/{target_id}", status_code=204)
async def delete_employee_target(
    target_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """删除个人目标规划层记录，不直接影响已生成绩效结果。"""
    try:
        result = await db.execute(select(EmployeeTarget).where(EmployeeTarget.id == target_id))
        record = result.scalar_one_or_none()
        if not record:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工目标不存在: {target_id}", status_code=404)
        delete_result = db.delete(record)
        if hasattr(delete_result, "__await__"):
            await delete_result
        await db.commit()
        return None
    except Exception as e:
        await db.rollback()
        logger.error("删除员工目标失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除员工目标失败: {str(e)}", status_code=500)
