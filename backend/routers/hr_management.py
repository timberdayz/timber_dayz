"""
HR管理API路由 v4.21.0
Description: 完整的人力资源管理模块，包括：
- 部门管理（树形结构）
- 职位管理（职级体系）
- 员工档案（业界标准字段）
- 考勤管理（排班、请假、加班）
- 薪酬管理（薪资结构、工资单）
- 绩效与提成查询

Created: 2025-01-31
Updated: 2025-01-30 (v4.21.0 业界标准优化)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal

from backend.models.database import get_async_db
from backend.routers.auth import get_current_user
from modules.core.db import (
    Department,
    Position,
    Employee,
    EmployeeTarget,
    WorkShift,
    AttendanceRecord,
    LeaveType,
    LeaveRecord,
    OvertimeRecord,
    SalaryStructure,
    PayrollRecord,
    SocialInsuranceConfig,
    EmployeePerformance,
    EmployeeCommission,
    ShopCommission,
    DimUser,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR管理"])


# ============================================================================
# Pydantic模型 - 部门管理
# ============================================================================

class DepartmentCreate(BaseModel):
    department_code: str = Field(..., description="部门编码", min_length=1, max_length=64)
    department_name: str = Field(..., description="部门名称", min_length=1, max_length=128)
    parent_id: Optional[int] = Field(None, description="上级部门ID")
    level: int = Field(1, ge=1, le=10, description="部门层级")
    sort_order: int = Field(0, ge=0, description="排序序号")
    manager_id: Optional[int] = Field(None, description="部门负责人ID")
    description: Optional[str] = Field(None, description="部门描述")
    status: str = Field("active", description="状态")


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    level: Optional[int] = Field(None, ge=1, le=10)
    sort_order: Optional[int] = Field(None, ge=0)
    manager_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: int
    department_code: str
    department_name: str
    parent_id: Optional[int]
    level: int
    sort_order: int
    manager_id: Optional[int]
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 职位管理
# ============================================================================

class PositionCreate(BaseModel):
    position_code: str = Field(..., description="职位编码", min_length=1, max_length=64)
    position_name: str = Field(..., description="职位名称", min_length=1, max_length=128)
    position_level: int = Field(1, ge=1, le=10, description="职级")
    department_id: Optional[int] = Field(None, description="所属部门ID")
    min_salary: Optional[Decimal] = Field(None, ge=0, description="薪资下限")
    max_salary: Optional[Decimal] = Field(None, ge=0, description="薪资上限")
    description: Optional[str] = Field(None, description="职位描述")
    requirements: Optional[str] = Field(None, description="任职要求")
    status: str = Field("active", description="状态")


class PositionUpdate(BaseModel):
    position_name: Optional[str] = Field(None, min_length=1, max_length=128)
    position_level: Optional[int] = Field(None, ge=1, le=10)
    department_id: Optional[int] = None
    min_salary: Optional[Decimal] = Field(None, ge=0)
    max_salary: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[str] = None


class PositionResponse(BaseModel):
    id: int
    position_code: str
    position_name: str
    position_level: int
    department_id: Optional[int]
    min_salary: Optional[Decimal]
    max_salary: Optional[Decimal]
    description: Optional[str]
    requirements: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 员工管理（业界标准字段）
# ============================================================================

class EmployeeCreate(BaseModel):
    """创建员工：employee_code 不传或为空时由后端自动生成（格式 EMP+年份后2位+4位流水号）"""
    employee_code: Optional[str] = Field(None, description="员工编号，不传则自动生成", max_length=64)
    name: str = Field(..., description="姓名", min_length=1, max_length=128)
    gender: Optional[str] = Field(None, description="性别:male/female/other")
    birth_date: Optional[date] = Field(None, description="出生日期")
    id_type: Optional[str] = Field("id_card", description="证件类型")
    id_number: Optional[str] = Field(None, description="证件号码")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    phone: Optional[str] = Field(None, description="手机号码")
    email: Optional[str] = Field(None, description="邮箱")
    address: Optional[str] = Field(None, description="现居地址")
    emergency_contact: Optional[str] = Field(None, description="紧急联系人")
    emergency_phone: Optional[str] = Field(None, description="紧急联系人电话")
    department_id: Optional[int] = Field(None, description="部门ID")
    position_id: Optional[int] = Field(None, description="职位ID")
    manager_id: Optional[int] = Field(None, description="直属上级ID")
    hire_date: Optional[date] = Field(None, description="入职日期")
    probation_end_date: Optional[date] = Field(None, description="试用期结束日期")
    contract_type: Optional[str] = Field(None, description="合同类型")
    contract_start_date: Optional[date] = Field(None, description="合同开始日期")
    contract_end_date: Optional[date] = Field(None, description="合同结束日期")
    bank_name: Optional[str] = Field(None, description="开户银行")
    bank_account: Optional[str] = Field(None, description="银行账号")
    status: str = Field("active", description="状态")
    user_id: Optional[int] = Field(None, description="关联登录账号 dim_users.user_id")

    @field_validator("birth_date", "hire_date", "probation_end_date", "contract_start_date", "contract_end_date", mode="before")
    @classmethod
    def empty_str_to_none_date(cls, v):
        if v is None or v == "":
            return None
        return v

    @field_validator(
        "gender", "id_type", "id_number", "avatar_url", "phone", "email", "address",
        "emergency_contact", "emergency_phone", "contract_type", "bank_name", "bank_account",
        "employee_code",
        mode="before",
    )
    @classmethod
    def empty_str_to_none_str(cls, v):
        if v is not None and isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("department_id", "position_id", "manager_id", mode="before")
    @classmethod
    def empty_to_none_int(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "active"
        return v


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_id: Optional[int] = None
    hire_date: Optional[date] = None
    probation_end_date: Optional[date] = None
    regularization_date: Optional[date] = None
    leave_date: Optional[date] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    status: Optional[str] = None
    user_id: Optional[int] = Field(None, description="关联登录账号 dim_users.user_id")


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    name: str
    gender: Optional[str]
    birth_date: Optional[date]
    id_type: Optional[str]
    id_number: Optional[str]
    avatar_url: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    emergency_contact: Optional[str]
    emergency_phone: Optional[str]
    department_id: Optional[int]
    position_id: Optional[int]
    manager_id: Optional[int]
    hire_date: Optional[date]
    probation_end_date: Optional[date]
    regularization_date: Optional[date]
    leave_date: Optional[date]
    contract_type: Optional[str]
    contract_start_date: Optional[date]
    contract_end_date: Optional[date]
    bank_name: Optional[str]
    bank_account: Optional[str]
    status: str
    username: Optional[str] = None  # 关联登录账号时展示
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 排班班次
# ============================================================================

class WorkShiftCreate(BaseModel):
    shift_code: str = Field(..., description="班次编码", min_length=1, max_length=64)
    shift_name: str = Field(..., description="班次名称", min_length=1, max_length=128)
    start_time: str = Field(..., description="上班时间(HH:MM)", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., description="下班时间(HH:MM)", pattern=r"^\d{2}:\d{2}$")
    work_hours: float = Field(8.0, ge=0, le=24, description="标准工作时长")
    break_hours: float = Field(1.0, ge=0, le=8, description="休息时长")
    late_tolerance: int = Field(15, ge=0, description="迟到容忍时间(分钟)")
    early_leave_tolerance: int = Field(15, ge=0, description="早退容忍时间(分钟)")
    is_flexible: bool = Field(False, description="是否弹性工时")
    status: str = Field("active", description="状态")


class WorkShiftResponse(BaseModel):
    id: int
    shift_code: str
    shift_name: str
    start_time: str
    end_time: str
    work_hours: float
    break_hours: float
    late_tolerance: int
    early_leave_tolerance: int
    is_flexible: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 考勤记录
# ============================================================================

class AttendanceRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    attendance_date: date = Field(..., description="考勤日期")
    clock_in_time: Optional[datetime] = Field(None, description="上班打卡时间")
    clock_out_time: Optional[datetime] = Field(None, description="下班打卡时间")
    clock_in_location: Optional[str] = Field(None, description="上班打卡位置")
    clock_out_location: Optional[str] = Field(None, description="下班打卡位置")
    clock_in_type: Optional[str] = Field("normal", description="上班打卡类型")
    clock_out_type: Optional[str] = Field("normal", description="下班打卡类型")
    shift_id: Optional[int] = Field(None, description="排班班次ID")
    work_hours: Optional[float] = Field(None, ge=0, le=24, description="实际工作时长")
    overtime_hours: Optional[float] = Field(0.0, ge=0, description="加班时长")
    status: str = Field("normal", description="考勤状态")
    remark: Optional[str] = Field(None, description="备注")


class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    clock_in_location: Optional[str] = None
    clock_out_location: Optional[str] = None
    clock_in_type: Optional[str] = None
    clock_out_type: Optional[str] = None
    shift_id: Optional[int] = None
    work_hours: Optional[float] = Field(None, ge=0, le=24)
    overtime_hours: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    remark: Optional[str] = None


class AttendanceRecordResponse(BaseModel):
    id: int
    employee_code: str
    attendance_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    clock_in_location: Optional[str]
    clock_out_location: Optional[str]
    clock_in_type: Optional[str]
    clock_out_type: Optional[str]
    shift_id: Optional[int]
    work_hours: Optional[float]
    overtime_hours: Optional[float]
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 假期类型
# ============================================================================

class LeaveTypeCreate(BaseModel):
    leave_code: str = Field(..., description="假期编码", min_length=1, max_length=64)
    leave_name: str = Field(..., description="假期名称", min_length=1, max_length=128)
    is_paid: bool = Field(True, description="是否带薪")
    max_days_per_year: Optional[float] = Field(None, ge=0, description="年度最大天数")
    requires_approval: bool = Field(True, description="是否需要审批")
    description: Optional[str] = Field(None, description="假期说明")
    status: str = Field("active", description="状态")


class LeaveTypeResponse(BaseModel):
    id: int
    leave_code: str
    leave_name: str
    is_paid: bool
    max_days_per_year: Optional[float]
    requires_approval: bool
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 请假记录
# ============================================================================

class LeaveRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    leave_type_id: int = Field(..., description="假期类型ID")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    days: float = Field(..., gt=0, description="请假天数")
    reason: Optional[str] = Field(None, description="请假原因")


class LeaveRecordUpdate(BaseModel):
    approval_status: Optional[str] = Field(None, description="审批状态")
    approver_id: Optional[int] = Field(None, description="审批人ID")
    approval_remark: Optional[str] = Field(None, description="审批备注")


class LeaveRecordResponse(BaseModel):
    id: int
    employee_code: str
    leave_type_id: int
    start_date: date
    end_date: date
    days: float
    reason: Optional[str]
    approver_id: Optional[int]
    approval_status: str
    approval_time: Optional[datetime]
    approval_remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 加班记录
# ============================================================================

class OvertimeRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    overtime_date: date = Field(..., description="加班日期")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    hours: float = Field(..., gt=0, description="加班时长")
    overtime_type: str = Field("workday", description="加班类型:workday/weekend/holiday")
    reason: Optional[str] = Field(None, description="加班原因")


class OvertimeRecordUpdate(BaseModel):
    approval_status: Optional[str] = Field(None, description="审批状态")
    approver_id: Optional[int] = Field(None, description="审批人ID")


class OvertimeRecordResponse(BaseModel):
    id: int
    employee_code: str
    overtime_date: date
    start_time: datetime
    end_time: datetime
    hours: float
    overtime_type: str
    reason: Optional[str]
    approver_id: Optional[int]
    approval_status: str
    approval_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 薪资结构
# ============================================================================

class SalaryStructureCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    base_salary: Decimal = Field(..., ge=0, description="基本工资")
    position_salary: Decimal = Field(0, ge=0, description="岗位工资")
    housing_allowance: Decimal = Field(0, ge=0, description="住房补贴")
    transport_allowance: Decimal = Field(0, ge=0, description="交通补贴")
    meal_allowance: Decimal = Field(0, ge=0, description="餐饮补贴")
    communication_allowance: Decimal = Field(0, ge=0, description="通讯补贴")
    other_allowance: Decimal = Field(0, ge=0, description="其他补贴")
    performance_ratio: float = Field(0, ge=0, le=1, description="绩效工资比例")
    commission_ratio: float = Field(0, ge=0, le=1, description="提成比例")
    social_insurance_base: Optional[Decimal] = Field(None, ge=0, description="社保基数")
    housing_fund_base: Optional[Decimal] = Field(None, ge=0, description="公积金基数")
    effective_date: date = Field(..., description="生效日期")
    status: str = Field("active", description="状态")


class SalaryStructureResponse(BaseModel):
    id: int
    employee_code: str
    base_salary: Decimal
    position_salary: Decimal
    housing_allowance: Decimal
    transport_allowance: Decimal
    meal_allowance: Decimal
    communication_allowance: Decimal
    other_allowance: Decimal
    performance_ratio: float
    commission_ratio: float
    social_insurance_base: Optional[Decimal]
    housing_fund_base: Optional[Decimal]
    effective_date: date
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 工资单
# ============================================================================

class PayrollRecordResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    base_salary: Decimal
    position_salary: Decimal
    performance_salary: Decimal
    overtime_pay: Decimal
    commission: Decimal
    allowances: Decimal
    bonus: Decimal
    gross_salary: Decimal
    social_insurance_personal: Decimal
    housing_fund_personal: Decimal
    income_tax: Decimal
    other_deductions: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    social_insurance_company: Decimal
    housing_fund_company: Decimal
    total_cost: Decimal
    status: str
    pay_date: Optional[date]
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 员工目标
# ============================================================================

class EmployeeTargetCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    year_month: str = Field(..., description="目标月份(YYYY-MM)", pattern=r"^\d{4}-\d{2}$")
    target_type: str = Field(..., description="目标类型(sales/orders/customers)", max_length=32)
    target_value: Decimal = Field(..., ge=0, description="目标值")


class EmployeeTargetUpdate(BaseModel):
    target_value: Optional[Decimal] = Field(None, ge=0)


class EmployeeTargetResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    target_type: str
    target_value: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pydantic模型 - 绩效与提成查询（只读）
# ============================================================================

class EmployeePerformanceResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    actual_sales: Decimal
    achievement_rate: float
    performance_score: float
    calculated_at: datetime

    class Config:
        from_attributes = True


class EmployeeCommissionResponse(BaseModel):
    id: int
    employee_code: str
    year_month: str
    sales_amount: Decimal
    commission_amount: Decimal
    commission_rate: float
    calculated_at: datetime

    class Config:
        from_attributes = True


class ShopCommissionResponse(BaseModel):
    id: int
    shop_id: str
    year_month: str
    sales_amount: Decimal
    commission_amount: Decimal
    commission_rate: float
    calculated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# 部门管理API
# ============================================================================

@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(
    parent_id: Optional[int] = Query(None, description="上级部门ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=500, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取部门列表（支持树形结构查询）"""
    try:
        query = select(Department)
        conditions = []
        
        if parent_id is not None:
            conditions.append(Department.parent_id == parent_id)
        if status:
            conditions.append(Department.status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(Department.sort_order, Department.id).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        departments = result.scalars().all()
        
        return [DepartmentResponse.model_validate(dept) for dept in departments]
    except Exception as e:
        logger.error(f"获取部门列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取部门列表失败: {str(e)}")


@router.get("/departments/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """获取部门详情"""
    try:
        result = await db.execute(
            select(Department).where(Department.id == department_id)
        )
        department = result.scalar_one_or_none()
        
        if not department:
            raise HTTPException(status_code=404, detail=f"部门不存在: {department_id}")
        
        return DepartmentResponse.model_validate(department)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取部门详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取部门详情失败: {str(e)}")


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
async def create_department(
    department: DepartmentCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建部门"""
    try:
        # 检查编码是否已存在
        existing = await db.execute(
            select(Department).where(Department.department_code == department.department_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"部门编码已存在: {department.department_code}")
        
        new_department = Department(**department.model_dump())
        db.add(new_department)
        await db.commit()
        await db.refresh(new_department)
        
        logger.info(f"创建部门成功: {department.department_code} - {department.department_name}")
        return DepartmentResponse.model_validate(new_department)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建部门失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建部门失败: {str(e)}")


@router.put("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新部门"""
    try:
        result = await db.execute(
            select(Department).where(Department.id == department_id)
        )
        department = result.scalar_one_or_none()
        
        if not department:
            raise HTTPException(status_code=404, detail=f"部门不存在: {department_id}")
        
        update_data = department_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(department, key, value)
        
        department.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(department)
        
        logger.info(f"更新部门成功: {department_id}")
        return DepartmentResponse.model_validate(department)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新部门失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新部门失败: {str(e)}")


@router.delete("/departments/{department_id}", status_code=204)
async def delete_department(
    department_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除部门（软删除）"""
    try:
        result = await db.execute(
            select(Department).where(Department.id == department_id)
        )
        department = result.scalar_one_or_none()
        
        if not department:
            raise HTTPException(status_code=404, detail=f"部门不存在: {department_id}")
        
        department.status = "inactive"
        department.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"删除部门成功(软删除): {department_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除部门失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除部门失败: {str(e)}")


# ============================================================================
# 职位管理API
# ============================================================================

@router.get("/positions", response_model=List[PositionResponse])
async def list_positions(
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=500, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取职位列表"""
    try:
        query = select(Position)
        conditions = []
        
        if department_id is not None:
            conditions.append(Position.department_id == department_id)
        if status:
            conditions.append(Position.status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(Position.position_level, Position.id).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        positions = result.scalars().all()
        
        return [PositionResponse.model_validate(pos) for pos in positions]
    except Exception as e:
        logger.error(f"获取职位列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取职位列表失败: {str(e)}")


@router.post("/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    position: PositionCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建职位"""
    try:
        existing = await db.execute(
            select(Position).where(Position.position_code == position.position_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"职位编码已存在: {position.position_code}")
        
        new_position = Position(**position.model_dump())
        db.add(new_position)
        await db.commit()
        await db.refresh(new_position)
        
        logger.info(f"创建职位成功: {position.position_code} - {position.position_name}")
        return PositionResponse.model_validate(new_position)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建职位失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建职位失败: {str(e)}")


@router.put("/positions/{position_id}", response_model=PositionResponse)
async def update_position(
    position_id: int,
    position_update: PositionUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新职位"""
    try:
        result = await db.execute(
            select(Position).where(Position.id == position_id)
        )
        position = result.scalar_one_or_none()
        
        if not position:
            raise HTTPException(status_code=404, detail=f"职位不存在: {position_id}")
        
        update_data = position_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(position, key, value)
        
        position.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(position)
        
        logger.info(f"更新职位成功: {position_id}")
        return PositionResponse.model_validate(position)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新职位失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新职位失败: {str(e)}")


@router.delete("/positions/{position_id}", status_code=204)
async def delete_position(
    position_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除职位（软删除）"""
    try:
        result = await db.execute(
            select(Position).where(Position.id == position_id)
        )
        position = result.scalar_one_or_none()
        
        if not position:
            raise HTTPException(status_code=404, detail=f"职位不存在: {position_id}")
        
        position.status = "inactive"
        position.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"删除职位成功(软删除): {position_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除职位失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除职位失败: {str(e)}")


# ============================================================================
# 员工管理API
# ============================================================================

async def _username_for_user_id(db: AsyncSession, user_id: Optional[int]) -> Optional[str]:
    """根据 dim_users.user_id 查询 username，用于 EmployeeResponse.username"""
    if not user_id:
        return None
    result = await db.execute(select(DimUser).where(DimUser.user_id == user_id))
    user = result.scalar_one_or_none()
    return user.username if user else None


class MeProfileUpdate(BaseModel):
    """我的档案：仅允许自助修改的字段"""
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=128)
    address: Optional[str] = Field(None, max_length=512)
    emergency_contact: Optional[str] = Field(None, max_length=128)
    emergency_phone: Optional[str] = Field(None, max_length=32)


@router.get("/me/profile", response_model=EmployeeResponse)
async def get_me_profile(
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的档案：当前登录用户关联的员工档案；未关联时首次访问自动创建最小员工并关联（系统主要面向内部员工，注册并登录即可用）。路由须在 /employees/{employee_code} 之前。"""
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.user_id))
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
            email=current_user.email,
        )
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
        logger.info(f"我的档案自动创建员工: {employee_code} (user_id={current_user.user_id})")
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


@router.put("/me/profile", response_model=EmployeeResponse)
async def put_me_profile(
    body: MeProfileUpdate,
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的档案：仅接受白名单字段 phone/email/address/emergency_contact/emergency_phone。"""
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="您尚未关联员工档案，请联系管理员")
    update_data = body.model_dump(exclude_unset=True)
    for key in ("phone", "email", "address", "emergency_contact", "emergency_phone"):
        if key in update_data:
            setattr(employee, key, update_data[key])
    employee.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(employee)
    username = await _username_for_user_id(db, employee.user_id)
    resp = EmployeeResponse.model_validate(employee)
    return resp.model_copy(update={"username": username})


class MyIncomeResponse(BaseModel):
    """我的收入响应"""
    linked: bool = True
    period: Optional[str] = None
    base_salary: Optional[float] = None
    commission_amount: Optional[float] = None
    commission_rate: Optional[float] = None
    performance_score: Optional[float] = None
    achievement_rate: Optional[float] = None
    total_income: Optional[float] = None
    breakdown: Optional[dict] = None


@router.get("/me/income", response_model=MyIncomeResponse)
async def get_my_income(
    year_month: Optional[str] = Query(None, description="月份(YYYY-MM)，不填则当月"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """我的收入：根据当前用户关联的员工返回收入数据；未关联时返回 linked: false。"""
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        return MyIncomeResponse(linked=False)
    period = year_month or datetime.utcnow().strftime("%Y-%m")
    employee_code = employee.employee_code
    base_salary = None
    commission_amount = 0.0
    performance_score = None
    achievement_rate = None
    breakdown = {}
    # 查询 payroll_records
    pr_result = await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.employee_code == employee_code,
            PayrollRecord.year_month == period
        )
    )
    pr = pr_result.scalar_one_or_none()
    if pr:
        base_salary = float(pr.base_salary) if pr.base_salary else None
        commission_amount = float(pr.commission or 0)
        breakdown["payroll"] = {"base_salary": base_salary, "commission": commission_amount, "net_salary": float(pr.net_salary or 0)}
    # 若无工资单，组合 salary_structures + employee_commissions + employee_performance
    if base_salary is None:
        ss_result = await db.execute(
            select(SalaryStructure).where(
                SalaryStructure.employee_code == employee_code,
                SalaryStructure.status == "active"
            ).order_by(SalaryStructure.effective_date.desc()).limit(1)
        )
        ss = ss_result.scalar_one_or_none()
        if ss:
            base_salary = float(ss.base_salary or 0) + float(ss.position_salary or 0)
            breakdown["salary_structure"] = {"base_salary": base_salary}
    ec_result = await db.execute(
        select(EmployeeCommission).where(
            EmployeeCommission.employee_code == employee_code,
            EmployeeCommission.year_month == period
        )
    )
    ec = ec_result.scalar_one_or_none()
    if ec:
        commission_amount = float(ec.commission_amount or 0)
        breakdown["commission"] = {"amount": commission_amount}
    ep_result = await db.execute(
        select(EmployeePerformance).where(
            EmployeePerformance.employee_code == employee_code,
            EmployeePerformance.year_month == period
        )
    )
    ep = ep_result.scalar_one_or_none()
    if ep:
        performance_score = float(ep.performance_score or 0)
        achievement_rate = float(ep.achievement_rate or 0)
        breakdown["performance"] = {"score": performance_score, "achievement_rate": achievement_rate}
    total = (base_salary or 0) + commission_amount
    return MyIncomeResponse(
        linked=True,
        period=period,
        base_salary=base_salary,
        commission_amount=commission_amount,
        performance_score=performance_score,
        achievement_rate=achievement_rate,
        total_income=total if (base_salary is not None or commission_amount) else None,
        breakdown=breakdown if breakdown else None
    )


@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    position_id: Optional[int] = Query(None, description="职位ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选(active/inactive/probation/leave)"),
    keyword: Optional[str] = Query(None, description="关键字搜索(姓名/工号)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工列表(分页、筛选)"""
    try:
        query = select(Employee)
        conditions = []
        
        if department_id is not None:
            conditions.append(Employee.department_id == department_id)
        if position_id is not None:
            conditions.append(Employee.position_id == position_id)
        if status:
            conditions.append(Employee.status == status)
        if keyword:
            conditions.append(
                or_(
                    Employee.name.ilike(f"%{keyword}%"),
                    Employee.employee_code.ilike(f"%{keyword}%")
                )
            )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(Employee.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        employees = result.scalars().all()
        out = []
        for emp in employees:
            resp = EmployeeResponse.model_validate(emp)
            resp = resp.model_copy(update={"username": await _username_for_user_id(db, emp.user_id)})
            out.append(resp)
        return out
    except Exception as e:
        logger.error(f"获取员工列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工列表失败: {str(e)}")


@router.get("/employees/count")
async def count_employees(
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工总数（用于人效计算等）"""
    try:
        query = select(func.count(Employee.id))
        
        if status:
            query = query.where(Employee.status == status)
        
        result = await db.execute(query)
        count = result.scalar()
        
        return {"count": count, "status": status or "all"}
    except Exception as e:
        logger.error(f"获取员工总数失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工总数失败: {str(e)}")


@router.get("/employees/{employee_code}", response_model=EmployeeResponse)
async def get_employee(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工详情"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"员工不存在: {employee_code}")
        username = await _username_for_user_id(db, employee.user_id)
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(update={"username": username})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取员工详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工详情失败: {str(e)}")


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
            seq = int(code[len(prefix):]) if len(code) > len(prefix) else 0
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    db: AsyncSession = Depends(get_async_db)
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
            raise HTTPException(status_code=400, detail=f"员工编号已存在: {employee_code}")

        user_id = data.get("user_id")
        if user_id is not None:
            other = await db.execute(select(Employee).where(Employee.user_id == user_id))
            if other.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="该登录账号已关联其他员工")

        new_employee = Employee(**data)
        db.add(new_employee)
        await db.commit()
        await db.refresh(new_employee)

        logger.info(f"创建员工成功: {new_employee.employee_code} - {new_employee.name}")
        username = await _username_for_user_id(db, new_employee.user_id)
        resp = EmployeeResponse.model_validate(new_employee)
        return resp.model_copy(update={"username": username})
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建员工失败: {str(e)}")


@router.put("/employees/{employee_code}", response_model=EmployeeResponse)
async def update_employee(
    employee_code: str,
    employee_update: EmployeeUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新员工信息"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"员工不存在: {employee_code}")
        
        update_data = employee_update.model_dump(exclude_unset=True)
        if "user_id" in update_data and update_data["user_id"] is not None:
            other = await db.execute(
                select(Employee).where(
                    Employee.user_id == update_data["user_id"],
                    Employee.id != employee.id
                )
            )
            if other.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="该登录账号已关联其他员工")
        for key, value in update_data.items():
            setattr(employee, key, value)
        
        employee.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(employee)
        
        logger.info(f"更新员工成功: {employee_code}")
        username = await _username_for_user_id(db, employee.user_id)
        resp = EmployeeResponse.model_validate(employee)
        return resp.model_copy(update={"username": username})
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新员工失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新员工失败: {str(e)}")


@router.delete("/employees/{employee_code}", status_code=204)
async def delete_employee(
    employee_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """删除员工(软删除:设置status为inactive)"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"员工不存在: {employee_code}")
        
        employee.status = "inactive"
        employee.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"删除员工成功(软删除): {employee_code}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除员工失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除员工失败: {str(e)}")


# ============================================================================
# 排班班次API
# ============================================================================

@router.get("/work-shifts", response_model=List[WorkShiftResponse])
async def list_work_shifts(
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取班次列表"""
    try:
        query = select(WorkShift)
        
        if status:
            query = query.where(WorkShift.status == status)
        
        query = query.order_by(WorkShift.shift_code)
        result = await db.execute(query)
        shifts = result.scalars().all()
        
        return [WorkShiftResponse.model_validate(shift) for shift in shifts]
    except Exception as e:
        logger.error(f"获取班次列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取班次列表失败: {str(e)}")


@router.post("/work-shifts", response_model=WorkShiftResponse, status_code=201)
async def create_work_shift(
    shift: WorkShiftCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建班次"""
    try:
        existing = await db.execute(
            select(WorkShift).where(WorkShift.shift_code == shift.shift_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"班次编码已存在: {shift.shift_code}")
        
        new_shift = WorkShift(**shift.model_dump())
        db.add(new_shift)
        await db.commit()
        await db.refresh(new_shift)
        
        logger.info(f"创建班次成功: {shift.shift_code} - {shift.shift_name}")
        return WorkShiftResponse.model_validate(new_shift)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建班次失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建班次失败: {str(e)}")


# ============================================================================
# 考勤记录API
# ============================================================================

@router.get("/attendance", response_model=List[AttendanceRecordResponse])
async def list_attendance_records(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    status: Optional[str] = Query(None, description="考勤状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取考勤记录列表(分页、筛选)"""
    try:
        query = select(AttendanceRecord)
        conditions = []
        
        if employee_code:
            conditions.append(AttendanceRecord.employee_code == employee_code)
        if start_date:
            conditions.append(AttendanceRecord.attendance_date >= start_date)
        if end_date:
            conditions.append(AttendanceRecord.attendance_date <= end_date)
        if status:
            conditions.append(AttendanceRecord.status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        records = result.scalars().all()
        
        return [AttendanceRecordResponse.model_validate(record) for record in records]
    except Exception as e:
        logger.error(f"获取考勤记录列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取考勤记录列表失败: {str(e)}")


@router.post("/attendance", response_model=AttendanceRecordResponse, status_code=201)
async def create_attendance_record(
    record: AttendanceRecordCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建考勤记录（打卡）"""
    try:
        # 检查员工是否存在
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == record.employee_code)
        )
        if not employee.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"员工不存在: {record.employee_code}")
        
        # 检查考勤记录是否已存在
        existing = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_code == record.employee_code,
                    AttendanceRecord.attendance_date == record.attendance_date
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"考勤记录已存在: {record.employee_code} - {record.attendance_date}"
            )
        
        # 自动计算工作时长
        work_hours = record.work_hours
        if record.clock_in_time and record.clock_out_time and work_hours is None:
            delta = record.clock_out_time - record.clock_in_time
            work_hours = delta.total_seconds() / 3600.0
        
        new_record = AttendanceRecord(**record.model_dump())
        if work_hours is not None:
            new_record.work_hours = work_hours
        
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建考勤记录成功: {record.employee_code} - {record.attendance_date}")
        return AttendanceRecordResponse.model_validate(new_record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建考勤记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建考勤记录失败: {str(e)}")


@router.put("/attendance/{record_id}", response_model=AttendanceRecordResponse)
async def update_attendance_record(
    record_id: int,
    record_update: AttendanceRecordUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新考勤记录"""
    try:
        result = await db.execute(
            select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"考勤记录不存在: {record_id}")
        
        update_data = record_update.model_dump(exclude_unset=True)
        
        # 如果更新了上下班时间，重新计算工作时长
        if (record_update.clock_in_time is not None or record_update.clock_out_time is not None) and record_update.work_hours is None:
            clock_in = record_update.clock_in_time if record_update.clock_in_time is not None else record.clock_in_time
            clock_out = record_update.clock_out_time if record_update.clock_out_time is not None else record.clock_out_time
            
            if clock_in and clock_out:
                delta = clock_out - clock_in
                update_data['work_hours'] = delta.total_seconds() / 3600.0
        
        for key, value in update_data.items():
            setattr(record, key, value)
        
        record.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(record)
        
        logger.info(f"更新考勤记录成功: {record_id}")
        return AttendanceRecordResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新考勤记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新考勤记录失败: {str(e)}")


# ============================================================================
# 假期类型API
# ============================================================================

@router.get("/leave-types", response_model=List[LeaveTypeResponse])
async def list_leave_types(
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取假期类型列表"""
    try:
        query = select(LeaveType)
        
        if status:
            query = query.where(LeaveType.status == status)
        
        query = query.order_by(LeaveType.leave_code)
        result = await db.execute(query)
        leave_types = result.scalars().all()
        
        return [LeaveTypeResponse.model_validate(lt) for lt in leave_types]
    except Exception as e:
        logger.error(f"获取假期类型列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取假期类型列表失败: {str(e)}")


@router.post("/leave-types", response_model=LeaveTypeResponse, status_code=201)
async def create_leave_type(
    leave_type: LeaveTypeCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建假期类型"""
    try:
        existing = await db.execute(
            select(LeaveType).where(LeaveType.leave_code == leave_type.leave_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"假期编码已存在: {leave_type.leave_code}")
        
        new_leave_type = LeaveType(**leave_type.model_dump())
        db.add(new_leave_type)
        await db.commit()
        await db.refresh(new_leave_type)
        
        logger.info(f"创建假期类型成功: {leave_type.leave_code} - {leave_type.leave_name}")
        return LeaveTypeResponse.model_validate(new_leave_type)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建假期类型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建假期类型失败: {str(e)}")


# ============================================================================
# 请假记录API
# ============================================================================

@router.get("/leave-records", response_model=List[LeaveRecordResponse])
async def list_leave_records(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    approval_status: Optional[str] = Query(None, description="审批状态筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取请假记录列表"""
    try:
        query = select(LeaveRecord)
        conditions = []
        
        if employee_code:
            conditions.append(LeaveRecord.employee_code == employee_code)
        if approval_status:
            conditions.append(LeaveRecord.approval_status == approval_status)
        if start_date:
            conditions.append(LeaveRecord.start_date >= start_date)
        if end_date:
            conditions.append(LeaveRecord.end_date <= end_date)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(LeaveRecord.created_at.desc()).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        records = result.scalars().all()
        
        return [LeaveRecordResponse.model_validate(record) for record in records]
    except Exception as e:
        logger.error(f"获取请假记录列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取请假记录列表失败: {str(e)}")


@router.post("/leave-records", response_model=LeaveRecordResponse, status_code=201)
async def create_leave_record(
    record: LeaveRecordCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建请假记录"""
    try:
        # 检查员工是否存在
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == record.employee_code)
        )
        if not employee.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"员工不存在: {record.employee_code}")
        
        new_record = LeaveRecord(**record.model_dump())
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建请假记录成功: {record.employee_code}")
        return LeaveRecordResponse.model_validate(new_record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建请假记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建请假记录失败: {str(e)}")


@router.put("/leave-records/{record_id}/approve", response_model=LeaveRecordResponse)
async def approve_leave_record(
    record_id: int,
    record_update: LeaveRecordUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """审批请假记录"""
    try:
        result = await db.execute(
            select(LeaveRecord).where(LeaveRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"请假记录不存在: {record_id}")
        
        update_data = record_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(record, key, value)
        
        if record_update.approval_status:
            record.approval_time = datetime.utcnow()
        
        record.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(record)
        
        logger.info(f"审批请假记录成功: {record_id}")
        return LeaveRecordResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"审批请假记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"审批请假记录失败: {str(e)}")


# ============================================================================
# 加班记录API
# ============================================================================

@router.get("/overtime-records", response_model=List[OvertimeRecordResponse])
async def list_overtime_records(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    approval_status: Optional[str] = Query(None, description="审批状态筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取加班记录列表"""
    try:
        query = select(OvertimeRecord)
        conditions = []
        
        if employee_code:
            conditions.append(OvertimeRecord.employee_code == employee_code)
        if approval_status:
            conditions.append(OvertimeRecord.approval_status == approval_status)
        if start_date:
            conditions.append(OvertimeRecord.overtime_date >= start_date)
        if end_date:
            conditions.append(OvertimeRecord.overtime_date <= end_date)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(OvertimeRecord.overtime_date.desc()).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        records = result.scalars().all()
        
        return [OvertimeRecordResponse.model_validate(record) for record in records]
    except Exception as e:
        logger.error(f"获取加班记录列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取加班记录列表失败: {str(e)}")


@router.post("/overtime-records", response_model=OvertimeRecordResponse, status_code=201)
async def create_overtime_record(
    record: OvertimeRecordCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建加班记录"""
    try:
        employee = await db.execute(
            select(Employee).where(Employee.employee_code == record.employee_code)
        )
        if not employee.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"员工不存在: {record.employee_code}")
        
        new_record = OvertimeRecord(**record.model_dump())
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建加班记录成功: {record.employee_code}")
        return OvertimeRecordResponse.model_validate(new_record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建加班记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建加班记录失败: {str(e)}")


# ============================================================================
# 薪资结构API
# ============================================================================

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
        raise HTTPException(status_code=500, detail=f"获取薪资结构列表失败: {str(e)}")


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
            raise HTTPException(status_code=404, detail=f"薪资结构不存在: {employee_code}")
        
        return SalaryStructureResponse.model_validate(structure)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取薪资结构失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取薪资结构失败: {str(e)}")


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
            raise HTTPException(status_code=400, detail=f"员工不存在: {structure.employee_code}")
        
        # 检查是否已存在
        existing = await db.execute(
            select(SalaryStructure).where(SalaryStructure.employee_code == structure.employee_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"薪资结构已存在: {structure.employee_code}")
        
        new_structure = SalaryStructure(**structure.model_dump())
        db.add(new_structure)
        await db.commit()
        await db.refresh(new_structure)
        
        logger.info(f"创建薪资结构成功: {structure.employee_code}")
        return SalaryStructureResponse.model_validate(new_structure)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建薪资结构失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建薪资结构失败: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"获取工资单列表失败: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"获取员工目标列表失败: {str(e)}")


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
            raise HTTPException(status_code=400, detail=f"员工不存在: {target.employee_code}")
        
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
            raise HTTPException(
                status_code=400,
                detail=f"员工目标已存在: {target.employee_code} - {target.year_month} - {target.target_type}"
            )
        
        new_target = EmployeeTarget(**target.model_dump())
        db.add(new_target)
        await db.commit()
        await db.refresh(new_target)
        
        logger.info(f"创建员工目标成功: {target.employee_code} - {target.year_month} - {target.target_type}")
        return EmployeeTargetResponse.model_validate(new_target)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工目标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建员工目标失败: {str(e)}")


# ============================================================================
# 绩效查询API（只读）
# ============================================================================

@router.get("/performance", response_model=List[EmployeePerformanceResponse])
async def list_employee_performance(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工绩效列表(从employee_performance表读取,由Metabase定时计算)"""
    try:
        query = select(EmployeePerformance)
        conditions = []
        
        if employee_code:
            conditions.append(EmployeePerformance.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeePerformance.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(EmployeePerformance.year_month.desc(), EmployeePerformance.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        performances = result.scalars().all()
        
        return [EmployeePerformanceResponse.model_validate(perf) for perf in performances]
    except Exception as e:
        logger.error(f"获取员工绩效列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工绩效列表失败: {str(e)}")


# ============================================================================
# 提成查询API（只读）
# ============================================================================

@router.get("/commissions/employee", response_model=List[EmployeeCommissionResponse])
async def list_employee_commissions(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工提成列表(从employee_commissions表读取,由Metabase定时计算)"""
    try:
        query = select(EmployeeCommission)
        conditions = []
        
        if employee_code:
            conditions.append(EmployeeCommission.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeeCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeCommission.year_month.desc(), EmployeeCommission.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [EmployeeCommissionResponse.model_validate(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取员工提成列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工提成列表失败: {str(e)}")


@router.get("/commissions/shop", response_model=List[ShopCommissionResponse])
async def list_shop_commissions(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选(YYYY-MM)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取店铺提成列表(从shop_commissions表读取,由Metabase定时计算)"""
    try:
        query = select(ShopCommission)
        conditions = []
        
        if shop_id:
            conditions.append(ShopCommission.shop_id == shop_id)
        if year_month:
            conditions.append(ShopCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        offset = (page - 1) * page_size
        query = query.order_by(ShopCommission.year_month.desc(), ShopCommission.shop_id).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [ShopCommissionResponse.model_validate(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取店铺提成列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取店铺提成列表失败: {str(e)}")
