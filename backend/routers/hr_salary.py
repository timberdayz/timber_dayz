"""
HR - 薪资与目标管理
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone
from decimal import Decimal

from backend.models.database import get_async_db
from backend.dependencies.auth import get_current_user
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger

logger = get_logger(__name__)
from backend.schemas.hr import (
    SalaryStructureCreate, SalaryStructureResponse,
    PayrollRecordResponse,
    EmployeeTargetCreate, EmployeeTargetResponse, EmployeeTargetUpdate,
)
from modules.core.db import (
    Employee, SalaryStructure, PayrollRecord, EmployeeTarget,
)

router = APIRouter(prefix="/api/hr", tags=["HR-薪资目标"])


@router.get("/salary-structures", response_model=List[SalaryStructureResponse])
async def list_salary_structures(
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取薪资结构列表"""
    try:
        query = select(SalaryStructure)
        
        if status:
            query = query.where(SalaryStructure.status == status)
        
        offset = (page - 1) * page_size
        query = query.order_by(SalaryStructure.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        structures = result.scalars().all()
        
        return [SalaryStructureResponse.model_validate(s) for s in structures]
    except Exception as e:
        logger.error(f"获取薪资结构列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取薪资结构列表失败: {str(e)}", status_code=500)


@router.get("/salary-structures/{employee_code}", response_model=SalaryStructureResponse)
async def get_salary_structure(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工薪资结构"""
    try:
        result = await db.execute(
            select(SalaryStructure).where(SalaryStructure.employee_code == employee_code)
        )
        structure = result.scalar_one_or_none()
        
        if not structure:
            return error_response(ErrorCode.DATA_NOT_FOUND, f"薪资结构不存在: {employee_code}", status_code=404)
        return SalaryStructureResponse.model_validate(structure)
    except Exception as e:
        logger.error(f"获取薪资结构失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取薪资结构失败: {str(e)}", status_code=500)


@router.post("/salary-structures", response_model=SalaryStructureResponse, status_code=201)
async def create_salary_structure(
    structure: SalaryStructureCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建薪资结构"""
    try:
        # 检查员工是否存在
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == structure.employee_code)
        )
        if not employee.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {structure.employee_code}", status_code=400)
        # 检查是否已存在
        existing = await db.execute(
            select(SalaryStructure).where(SalaryStructure.employee_code == structure.employee_code)
        )
        if existing.scalar_one_or_none():
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"薪资结构已存在: {structure.employee_code}", status_code=400)
        new_structure = SalaryStructure(**structure.model_dump())
        db.add(new_structure)
        await db.commit()
        await db.refresh(new_structure)
        logger.info(f"创建薪资结构成功: {structure.employee_code}")
        return SalaryStructureResponse.model_validate(new_structure)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建薪资结构失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建薪资结构失败: {str(e)}", status_code=500)


# ============================================================================
# 工资单API
# ============================================================================

@router.get("/payroll-records", response_model=List[PayrollRecordResponse])
async def list_payroll_records(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="工资月份筛选(YYYY-MM)"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取工资单列表"""
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
        
        offset = (page - 1) * page_size
        query = query.order_by(PayrollRecord.year_month.desc(), PayrollRecord.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        records = result.scalars().all()
        
        return [PayrollRecordResponse.model_validate(record) for record in records]
    except Exception as e:
        logger.error(f"获取工资单列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取工资单列表失败: {str(e)}", status_code=500)


# ============================================================================
# 员工目标管理API
# ============================================================================

@router.get("/employee-targets", response_model=List[EmployeeTargetResponse])
async def list_employee_targets(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    target_type: Optional[str] = Query(None, description="目标类型筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工目标列表(分页、筛选)"""
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
        
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeTarget.year_month.desc(), EmployeeTarget.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        targets = result.scalars().all()
        
        return [EmployeeTargetResponse.model_validate(target) for target in targets]
    except Exception as e:
        logger.error(f"获取员工目标列表失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取员工目标列表失败: {str(e)}", status_code=500)


@router.post("/employee-targets", response_model=EmployeeTargetResponse, status_code=201)
async def create_employee_target(
    target: EmployeeTargetCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建员工目标"""
    try:
        # 检查员工是否存在
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == target.employee_code)
        )
        if not employee.scalar_one_or_none():
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {target.employee_code}", status_code=400)
        # 检查目标是否已存在
        existing = await db.execute(
            select(EmployeeTarget).where(
                and_(
                    EmployeeTarget.employee_code == target.employee_code,
                    EmployeeTarget.year_month == target.year_month,
                    EmployeeTarget.target_type == target.target_type
                )
            )
        )
        if existing.scalar_one_or_none():
            return error_response(
                ErrorCode.DATA_ALREADY_EXISTS,
                f"员工目标已存在: {target.employee_code} - {target.year_month} - {target.target_type}",
                status_code=400,
            )
        new_target = EmployeeTarget(**target.model_dump())
        db.add(new_target)
        await db.commit()
        await db.refresh(new_target)
        logger.info(f"创建员工目标成功: {target.employee_code} - {target.year_month} - {target.target_type}")
        return EmployeeTargetResponse.model_validate(new_target)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工目标失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建员工目标失败: {str(e)}", status_code=500)


# ============================================================================
# 绩效查询API（只读）
# ============================================================================
