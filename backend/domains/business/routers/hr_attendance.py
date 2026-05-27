"""
HR - 考勤管理 (排班/考勤/请假/加班)
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
    WorkShiftCreate, WorkShiftResponse,
    AttendanceRecordCreate, AttendanceRecordResponse, AttendanceRecordUpdate,
    LeaveTypeCreate, LeaveTypeResponse,
    LeaveRecordCreate, LeaveRecordResponse, LeaveRecordUpdate,
    OvertimeRecordCreate, OvertimeRecordResponse, OvertimeRecordUpdate,
)
from modules.core.db import (
    Employee, WorkShift, AttendanceRecord,
    LeaveType, LeaveRecord, OvertimeRecord,
)

router = APIRouter(prefix="/api/hr", tags=["HR-考勤管理"])

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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取班次列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"班次编码已存在: {shift.shift_code}", status_code=400)
        new_shift = WorkShift(**shift.model_dump())
        db.add(new_shift)
        await db.commit()
        await db.refresh(new_shift)
        logger.info(f"创建班次成功: {shift.shift_code} - {shift.shift_name}")
        return WorkShiftResponse.model_validate(new_shift)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建班次失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建班次失败: {str(e)}", status_code=500)


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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取考勤记录列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {record.employee_code}", status_code=400)
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
            return error_response(
                ErrorCode.DATA_ALREADY_EXISTS,
                f"考勤记录已存在: {record.employee_code} - {record.attendance_date}",
                status_code=400,
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
    except Exception as e:
        await db.rollback()
        logger.error(f"创建考勤记录失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建考勤记录失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"考勤记录不存在: {record_id}", status_code=404)
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
        
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        
        logger.info(f"更新考勤记录成功: {record_id}")
        return AttendanceRecordResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新考勤记录失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新考勤记录失败: {str(e)}", status_code=500)


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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取假期类型列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"假期编码已存在: {leave_type.leave_code}", status_code=400)
        new_leave_type = LeaveType(**leave_type.model_dump())
        db.add(new_leave_type)
        await db.commit()
        await db.refresh(new_leave_type)
        
        logger.info(f"创建假期类型成功: {leave_type.leave_code} - {leave_type.leave_name}")
        return LeaveTypeResponse.model_validate(new_leave_type)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建假期类型失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建假期类型失败: {str(e)}", status_code=500)


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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取请假记录列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {record.employee_code}", status_code=400)
        new_record = LeaveRecord(**record.model_dump())
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建请假记录成功: {record.employee_code}")
        return LeaveRecordResponse.model_validate(new_record)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建请假记录失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建请假记录失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"请假记录不存在: {record_id}", status_code=404)
        update_data = record_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(record, key, value)
        
        if record_update.approval_status:
            record.approval_time = datetime.now(timezone.utc)
        
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        
        logger.info(f"审批请假记录成功: {record_id}")
        return LeaveRecordResponse.model_validate(record)
    except Exception as e:
        await db.rollback()
        logger.error(f"审批请假记录失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"审批请假记录失败: {str(e)}", status_code=500)


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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取加班记录列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"员工不存在: {record.employee_code}", status_code=400)
        new_record = OvertimeRecord(**record.model_dump())
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        
        logger.info(f"创建加班记录成功: {record.employee_code}")
        return OvertimeRecordResponse.model_validate(new_record)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建加班记录失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建加班记录失败: {str(e)}", status_code=500)


# ============================================================================
# 薪资结构API
# ============================================================================
