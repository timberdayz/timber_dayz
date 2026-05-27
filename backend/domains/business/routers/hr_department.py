"""
HR - 部门与职位管理
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
    DepartmentCreate, DepartmentResponse, DepartmentUpdate,
    PositionCreate, PositionResponse, PositionUpdate,
)
from modules.core.db import Department, Position

router = APIRouter(prefix="/api/hr", tags=["HR-部门职位"])

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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取部门列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"部门不存在: {department_id}", status_code=404)
        return DepartmentResponse.model_validate(department)
    except Exception as e:
        logger.error(f"获取部门详情失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取部门详情失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"部门编码已存在: {department.department_code}", status_code=400)
        new_department = Department(**department.model_dump())
        db.add(new_department)
        await db.commit()
        await db.refresh(new_department)
        logger.info(f"创建部门成功: {department.department_code} - {department.department_name}")
        return DepartmentResponse.model_validate(new_department)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建部门失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建部门失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"部门不存在: {department_id}", status_code=404)
        update_data = department_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(department, key, value)
        department.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(department)
        logger.info(f"更新部门成功: {department_id}")
        return DepartmentResponse.model_validate(department)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新部门失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新部门失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"部门不存在: {department_id}", status_code=404)
        department.status = "inactive"
        department.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"删除部门成功(软删除): {department_id}")
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"删除部门失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除部门失败: {str(e)}", status_code=500)


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
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取职位列表失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_ALREADY_EXISTS, f"职位编码已存在: {position.position_code}", status_code=400)
        new_position = Position(**position.model_dump())
        db.add(new_position)
        await db.commit()
        await db.refresh(new_position)
        logger.info(f"创建职位成功: {position.position_code} - {position.position_name}")
        return PositionResponse.model_validate(new_position)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建职位失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"创建职位失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"职位不存在: {position_id}", status_code=404)
        update_data = position_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(position, key, value)
        position.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(position)
        logger.info(f"更新职位成功: {position_id}")
        return PositionResponse.model_validate(position)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新职位失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"更新职位失败: {str(e)}", status_code=500)


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
            return error_response(ErrorCode.DATA_NOT_FOUND, f"职位不存在: {position_id}", status_code=404)
        position.status = "inactive"
        position.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"删除职位成功(软删除): {position_id}")
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"删除职位失败: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除职位失败: {str(e)}", status_code=500)

