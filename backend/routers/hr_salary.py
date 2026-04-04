from __future__ import annotations

"""
HR - 薪资与目标管理
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.schemas.hr import (
    EmployeeTargetCreate,
    EmployeeTargetResponse,
    EmployeeTargetUpdate,
    PayrollRecordManualUpdate,
    PayrollRecordResponse,
    SalaryStructureCreate,
    SalaryStructureResponse,
)
from backend.services.payroll_generation_service import PayrollGenerationService
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.db import DimUser, Employee, EmployeeTarget, PayrollRecord, SalaryStructure
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR-薪资目标"])


def _is_admin_user(current_user: DimUser) -> bool:
    if getattr(current_user, "is_superuser", False):
        return True
    return any(
        (hasattr(role, "role_code") and role.role_code == "admin")
        or (hasattr(role, "role_name") and role.role_name == "admin")
        for role in getattr(current_user, "roles", []) or []
    )


def _payroll_success(record: PayrollRecord) -> Dict[str, Any]:
    return {
        "success": True,
        "data": PayrollRecordResponse.model_validate(record).model_dump(mode="json"),
    }


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
        result = await db.execute(
            select(SalaryStructure).where(SalaryStructure.employee_code == employee_code)
        )
        structure = result.scalar_one_or_none()
        if not structure:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"薪资结构不存在: {employee_code}", status_code=404)
        return SalaryStructureResponse.model_validate(structure)
    except Exception as e:
        logger.error("获取薪资结构失败: %s", e, exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取薪资结构失败: {str(e)}", status_code=500)


@router.post("/salary-structures", response_model=SalaryStructureResponse, status_code=201)
async def create_salary_structure(
    structure: SalaryStructureCreate,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == structure.employee_code)
        )
        if not employee.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {structure.employee_code}", status_code=400)

        existing = await db.execute(
            select(SalaryStructure).where(SalaryStructure.employee_code == structure.employee_code)
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
        return _payroll_success(record)
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
        if not _is_admin_user(current_user):
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
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
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
