"""
角色管理API路由
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_db, get_async_db
from modules.core.db import DimRole, DimUser  # v4.12.0 SSOT迁移
from backend.schemas.auth import RoleCreate, RoleUpdate, RoleResponse, PermissionResponse
from backend.routers.auth import get_current_user
from backend.services.audit_service import audit_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from typing import List

router = APIRouter(prefix="/roles", tags=["角色管理"])

async def require_admin(current_user: DimUser = Depends(get_current_user)):
    """要求管理员权限"""
    if not any(role.name == "admin" for role in current_user.roles):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    return current_user

@router.post("/", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """创建角色"""
    # 检查角色名是否已存在
    result = await db.execute(select(DimRole).where(DimRole.name == role_data.name))
    existing_role = result.scalar_one_or_none()
    if existing_role:
        return error_response(
            code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
            message="Role already exists",
            error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
            recovery_suggestion="请使用不同的角色名称",
            status_code=400
        )
    
    # 创建角色
    role = DimRole(
        name=role_data.name,
        description=role_data.description,
        permissions=role_data.permissions
    )
    
    db.add(role)
    await db.commit()
    await db.refresh(role)
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.id,
        action="create_role",
        resource="role",
        resource_id=str(role.id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"role_name": role.name}
    )
    
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=role.permissions,
        created_at=role.created_at
    )

@router.get("/", response_model=List[RoleResponse])
async def get_roles(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取角色列表"""
    result = await db.execute(select(DimRole))
    roles = result.scalars().all()
    
    return [
        RoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=role.permissions,
            created_at=role.created_at
        )
        for role in roles
    ]

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取角色详情"""
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))  # v4.12.0修复：使用role_id字段
    role = result.scalar_one_or_none()
    if not role:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="Role not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查角色ID是否正确，或确认该角色已创建",
            status_code=404
        )
    
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=role.permissions,
        created_at=role.created_at
    )

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """更新角色信息"""
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))  # v4.12.0修复：使用role_id字段
    role = result.scalar_one_or_none()
    if not role:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="Role not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查角色ID是否正确，或确认该角色已创建",
            status_code=404
        )
    
    # 更新角色信息
    if role_update.description is not None:
        role.description = role_update.description
    
    if role_update.permissions is not None:
        role.permissions = role_update.permissions
    
    await db.commit()
    await db.refresh(role)
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.id,
        action="update_role",
        resource="role",
        resource_id=str(role.id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details=role_update.dict(exclude_unset=True)
    )
    
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=role.permissions,
        created_at=role.created_at
    )

@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """删除角色"""
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))  # v4.12.0修复：使用role_id字段
    role = result.scalar_one_or_none()
    if not role:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="Role not found",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请检查角色ID是否正确，或确认该角色已创建",
            status_code=404
        )
    
    # 检查是否有用户使用此角色
    from sqlalchemy import func
    from modules.core.db import DimUser, user_roles  # v4.12.0 SSOT迁移
    # 通过关联表查询使用此角色的用户数量
    count_result = await db.execute(
        select(func.count(user_roles.c.user_id)).where(user_roles.c.role_id == role_id)
    )
    users_with_role = count_result.scalar() or 0
    
    if users_with_role > 0:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="Cannot delete role that is assigned to users",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            recovery_suggestion="请先移除该角色的所有用户，然后再删除角色",
            status_code=400
        )
    
    # 记录操作
    await audit_service.log_action(
        user_id=current_user.id,
        action="delete_role",
        resource="role",
        resource_id=str(role.id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"role_name": role.name}
    )
    
    await db.delete(role)
    await db.commit()
    
    return success_response(
        data={"role_id": role_id},
        message="角色删除成功"
    )

@router.get("/permissions/available", response_model=List[PermissionResponse])
async def get_available_permissions(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取可用权限列表"""
    # 定义系统权限
    permissions = [
        PermissionResponse(
            id=1,
            name="business-overview",
            description="业务概览",
            resource="dashboard",
            action="read"
        ),
        PermissionResponse(
            id=2,
            name="sales-analysis",
            description="销售分析",
            resource="sales",
            action="read"
        ),
        PermissionResponse(
            id=3,
            name="sales-dashboard",
            description="销售看板",
            resource="dashboard",
            action="read"
        ),
        PermissionResponse(
            id=4,
            name="inventory-management",
            description="库存管理",
            resource="inventory",
            action="all"
        ),
        PermissionResponse(
            id=5,
            name="financial-management",
            description="财务管理",
            resource="finance",
            action="all"
        ),
        PermissionResponse(
            id=6,
            name="store-management",
            description="店铺管理",
            resource="store",
            action="all"
        ),
        PermissionResponse(
            id=7,
            name="user-management",
            description="用户管理",
            resource="user",
            action="all"
        ),
        PermissionResponse(
            id=8,
            name="role-management",
            description="角色管理",
            resource="role",
            action="all"
        ),
        PermissionResponse(
            id=9,
            name="system-settings",
            description="系统设置",
            resource="system",
            action="all"
        ),
        PermissionResponse(
            id=10,
            name="field-mapping",
            description="字段映射",
            resource="mapping",
            action="all"
        )
    ]
    
    return permissions
