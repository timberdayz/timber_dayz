"""
HR管理API路由
Description: 员工管理、员工目标、考勤记录、绩效查询的CRUD操作
Created: 2025-01-31
v4.6.0 DSS架构重构：HR管理模块API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field
from decimal import Decimal

from backend.models.database import get_db, get_async_db
from modules.core.db import (
    Employee,
    EmployeeTarget,
    AttendanceRecord,
    EmployeePerformance,
    EmployeeCommission,
    ShopCommission
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR管理"])


# ============================================================================
# Pydantic模型
# ============================================================================

# 员工管理
class EmployeeCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    name: str = Field(..., description="姓名", min_length=1, max_length=128)
    department: Optional[str] = Field(None, description="部门", max_length=128)
    position: Optional[str] = Field(None, description="职位", max_length=128)
    hire_date: Optional[date] = Field(None, description="入职日期")
    status: str = Field("active", description="状态（active/inactive）")


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    department: Optional[str] = Field(None, max_length=128)
    position: Optional[str] = Field(None, max_length=128)
    hire_date: Optional[date] = None
    status: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    name: str
    department: Optional[str]
    position: Optional[str]
    hire_date: Optional[date]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 员工目标
class EmployeeTargetCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    year_month: str = Field(..., description="目标月份（YYYY-MM）", pattern=r"^\d{4}-\d{2}$")
    target_type: str = Field(..., description="目标类型（sales/orders/customers）", max_length=32)
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


# 考勤记录
class AttendanceRecordCreate(BaseModel):
    employee_code: str = Field(..., description="员工编号", min_length=1, max_length=64)
    attendance_date: date = Field(..., description="考勤日期")
    clock_in_time: Optional[datetime] = Field(None, description="上班时间")
    clock_out_time: Optional[datetime] = Field(None, description="下班时间")
    work_hours: Optional[float] = Field(None, ge=0, le=24, description="工作时长（小时）")
    status: str = Field("normal", description="考勤状态（normal/late/early_leave/absent）")


class AttendanceRecordUpdate(BaseModel):
    clock_in_time: Optional[datetime] = None
    clock_out_time: Optional[datetime] = None
    work_hours: Optional[float] = Field(None, ge=0, le=24)
    status: Optional[str] = None


class AttendanceRecordResponse(BaseModel):
    id: int
    employee_code: str
    attendance_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    work_hours: Optional[float]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 绩效查询
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


# 提成查询
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
# 员工管理API
# ============================================================================

@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    department: Optional[str] = Query(None, description="部门筛选"),
    status: Optional[str] = Query(None, description="状态筛选（active/inactive）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工列表（分页、筛选）"""
    try:
        query = select(Employee)
        
        # 筛选条件
        conditions = []
        if department:
            conditions.append(Employee.department == department)
        if status:
            conditions.append(Employee.status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(Employee.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        employees = result.scalars().all()
        
        return [EmployeeResponse.from_orm(emp) for emp in employees]
    except Exception as e:
        logger.error(f"获取员工列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工列表失败: {str(e)}")


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
        
        return EmployeeResponse.from_orm(employee)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取员工详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工详情失败: {str(e)}")


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建员工"""
    try:
        # 检查员工编号是否已存在
        existing = db.execute(
            select(Employee).where(Employee.employee_code == employee.employee_code)
        ).scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=400, detail=f"员工编号已存在: {employee.employee_code}")
        
        # 创建员工
        new_employee = Employee(
            employee_code=employee.employee_code,
            name=employee.name,
            department=employee.department,
            position=employee.position,
            hire_date=employee.hire_date,
            status=employee.status
        )
        
        db.add(new_employee)
        await db.commit()
        await db.refresh(new_employee)
        
        logger.info(f"创建员工成功: {employee.employee_code} - {employee.name}")
        return EmployeeResponse.from_orm(new_employee)
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
        
        # 更新字段
        update_data = employee_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(employee, key, value)
        
        employee.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(employee)
        
        logger.info(f"更新员工成功: {employee_code}")
        return EmployeeResponse.from_orm(employee)
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
    """删除员工（软删除：设置status为inactive）"""
    try:
        result = await db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        employee = result.scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"员工不存在: {employee_code}")
        
        # 软删除：设置status为inactive
        employee.status = "inactive"
        employee.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"删除员工成功（软删除）: {employee_code}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除员工失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除员工失败: {str(e)}")


# ============================================================================
# 员工目标管理API
# ============================================================================

@router.get("/employee-targets", response_model=List[EmployeeTargetResponse])
async def list_employee_targets(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选（YYYY-MM）"),
    target_type: Optional[str] = Query(None, description="目标类型筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工目标列表（分页、筛选）"""
    try:
        query = select(EmployeeTarget)
        
        # 筛选条件
        conditions = []
        if employee_code:
            conditions.append(EmployeeTarget.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeeTarget.year_month == year_month)
        if target_type:
            conditions.append(EmployeeTarget.target_type == target_type)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeTarget.year_month.desc(), EmployeeTarget.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        targets = result.scalars().all()
        
        return [EmployeeTargetResponse.from_orm(target) for target in targets]
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
        employee = db.execute(
            select(Employee).where(Employee.employee_code == target.employee_code)
        ).scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=400, detail=f"员工不存在: {target.employee_code}")
        
        # 检查目标是否已存在
        existing = db.execute(
            select(EmployeeTarget).where(
                and_(
                    EmployeeTarget.employee_code == target.employee_code,
                    EmployeeTarget.year_month == target.year_month,
                    EmployeeTarget.target_type == target.target_type
                )
            )
        ).scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"员工目标已存在: {target.employee_code} - {target.year_month} - {target.target_type}"
            )
        
        # 创建目标
        new_target = EmployeeTarget(
            employee_code=target.employee_code,
            year_month=target.year_month,
            target_type=target.target_type,
            target_value=target.target_value
        )
        
        db.add(new_target)
        await db.commit()
        await db.refresh(new_target)
        
        logger.info(f"创建员工目标成功: {target.employee_code} - {target.year_month} - {target.target_type}")
        return EmployeeTargetResponse.from_orm(new_target)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建员工目标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建员工目标失败: {str(e)}")


@router.put("/employee-targets/{target_id}", response_model=EmployeeTargetResponse)
async def update_employee_target(
    target_id: int,
    target_update: EmployeeTargetUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新员工目标"""
    try:
        result = await db.execute(
            select(EmployeeTarget).where(EmployeeTarget.id == target_id)
        )
        target = result.scalar_one_or_none()
        
        if not target:
            raise HTTPException(status_code=404, detail=f"员工目标不存在: {target_id}")
        
        # 更新字段
        if target_update.target_value is not None:
            target.target_value = target_update.target_value
        
        target.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(target)
        
        logger.info(f"更新员工目标成功: {target_id}")
        return EmployeeTargetResponse.from_orm(target)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新员工目标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新员工目标失败: {str(e)}")


@router.delete("/employee-targets/{target_id}", status_code=204)
async def delete_employee_target(
    target_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除员工目标"""
    try:
        result = await db.execute(
            select(EmployeeTarget).where(EmployeeTarget.id == target_id)
        )
        target = result.scalar_one_or_none()
        
        if not target:
            raise HTTPException(status_code=404, detail=f"员工目标不存在: {target_id}")
        
        await db.delete(target)
        await db.commit()
        
        logger.info(f"删除员工目标成功: {target_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除员工目标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除员工目标失败: {str(e)}")


# ============================================================================
# 考勤管理API
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
    """获取考勤记录列表（分页、筛选）"""
    try:
        query = select(AttendanceRecord)
        
        # 筛选条件
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
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        records = result.scalars().all()
        
        return [AttendanceRecordResponse.from_orm(record) for record in records]
    except Exception as e:
        logger.error(f"获取考勤记录列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取考勤记录列表失败: {str(e)}")


@router.post("/attendance", response_model=AttendanceRecordResponse, status_code=201)
async def create_attendance_record(
    record: AttendanceRecordCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建考勤记录"""
    try:
        # 检查员工是否存在
        employee = db.execute(
            select(Employee).where(Employee.employee_code == record.employee_code)
        ).scalar_one_or_none()
        
        if not employee:
            raise HTTPException(status_code=400, detail=f"员工不存在: {record.employee_code}")
        
        # 检查考勤记录是否已存在
        existing = db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_code == record.employee_code,
                    AttendanceRecord.attendance_date == record.attendance_date
                )
            )
        ).scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"考勤记录已存在: {record.employee_code} - {record.attendance_date}"
            )
        
        # 自动计算工作时长（如果提供了上下班时间）
        work_hours = record.work_hours
        if record.clock_in_time and record.clock_out_time and work_hours is None:
            delta = record.clock_out_time - record.clock_in_time
            work_hours = delta.total_seconds() / 3600.0
        
        # 创建考勤记录
        new_record = AttendanceRecord(
            employee_code=record.employee_code,
            attendance_date=record.attendance_date,
            clock_in_time=record.clock_in_time,
            clock_out_time=record.clock_out_time,
            work_hours=work_hours,
            status=record.status
        )
        
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建考勤记录成功: {record.employee_code} - {record.attendance_date}")
        return AttendanceRecordResponse.from_orm(new_record)
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
        
        # 更新字段
        update_data = record_update.dict(exclude_unset=True)
        
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
        return AttendanceRecordResponse.from_orm(record)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新考勤记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新考勤记录失败: {str(e)}")


@router.delete("/attendance/{record_id}", status_code=204)
async def delete_attendance_record(
    record_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除考勤记录"""
    try:
        result = await db.execute(
            select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail=f"考勤记录不存在: {record_id}")
        
        await db.delete(record)
        await db.commit()
        
        logger.info(f"删除考勤记录成功: {record_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除考勤记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除考勤记录失败: {str(e)}")


# ============================================================================
# 绩效查询API
# ============================================================================

@router.get("/performance", response_model=List[EmployeePerformanceResponse])
async def list_employee_performance(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选（YYYY-MM）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工绩效列表（从employee_performance表读取，由Metabase定时计算）"""
    try:
        query = select(EmployeePerformance)
        
        # 筛选条件
        conditions = []
        if employee_code:
            conditions.append(EmployeePerformance.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeePerformance.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(EmployeePerformance.year_month.desc(), EmployeePerformance.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        performances = result.scalars().all()
        
        return [EmployeePerformanceResponse.from_orm(perf) for perf in performances]
    except Exception as e:
        logger.error(f"获取员工绩效列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工绩效列表失败: {str(e)}")


# ============================================================================
# 提成查询API
# ============================================================================

@router.get("/commissions/employee", response_model=List[EmployeeCommissionResponse])
async def list_employee_commissions(
    employee_code: Optional[str] = Query(None, description="员工编号筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选（YYYY-MM）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取员工提成列表（从employee_commissions表读取，由Metabase定时计算）"""
    try:
        query = select(EmployeeCommission)
        
        # 筛选条件
        conditions = []
        if employee_code:
            conditions.append(EmployeeCommission.employee_code == employee_code)
        if year_month:
            conditions.append(EmployeeCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(EmployeeCommission.year_month.desc(), EmployeeCommission.employee_code).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [EmployeeCommissionResponse.from_orm(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取员工提成列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取员工提成列表失败: {str(e)}")


@router.get("/commissions/shop", response_model=List[ShopCommissionResponse])
async def list_shop_commissions(
    shop_id: Optional[str] = Query(None, description="店铺ID筛选"),
    year_month: Optional[str] = Query(None, description="目标月份筛选（YYYY-MM）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取店铺提成列表（从shop_commissions表读取，由Metabase定时计算）"""
    try:
        query = select(ShopCommission)
        
        # 筛选条件
        conditions = []
        if shop_id:
            conditions.append(ShopCommission.shop_id == shop_id)
        if year_month:
            conditions.append(ShopCommission.year_month == year_month)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(ShopCommission.year_month.desc(), ShopCommission.shop_id).offset(offset).limit(page_size)
        
        result = await db.execute(query)
        commissions = result.scalars().all()
        
        return [ShopCommissionResponse.from_orm(comm) for comm in commissions]
    except Exception as e:
        logger.error(f"获取店铺提成列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取店铺提成列表失败: {str(e)}")

