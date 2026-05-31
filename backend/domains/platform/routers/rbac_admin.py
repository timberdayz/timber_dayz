from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.auth import RoleCreate, RoleUpdate
from backend.schemas.permission import (
    PermissionListResponse,
    PermissionResponse,
    PermissionTreeNode,
    PermissionTreeResponse,
)
from backend.services.audit_service import audit_service
from backend.services.rbac_service import get_rbac_service
from backend.utils.api_response import success_response
from modules.core.db import DimRole, DimUser, user_roles

router = APIRouter(prefix="/api/admin", tags=["RBAC 管理"])


def _convert_tree_node(data: dict) -> PermissionTreeNode:
    children = data.get("children") or None
    return PermissionTreeNode(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        resource=data["resource"],
        action=data.get("action"),
        category=data.get("category"),
        children=[_convert_tree_node(item) for item in children] if children else None,
    )


@router.get("/permissions", response_model=PermissionListResponse)
async def list_admin_permissions(current_user=Depends(require_admin)):
    service = get_rbac_service()
    permissions = [PermissionResponse(**item) for item in service.get_permission_catalog()]
    return PermissionListResponse(success=True, data=permissions, total=len(permissions))


@router.get("/permissions/tree", response_model=PermissionTreeResponse)
async def get_admin_permission_tree(current_user=Depends(require_admin)):
    service = get_rbac_service()
    tree = [_convert_tree_node(item) for item in service._permission_service.build_permission_tree()]
    return PermissionTreeResponse(success=True, data=tree)


@router.get("/rbac/assignable-roles")
async def get_assignable_roles(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole).where(DimRole.is_active.is_(True)).order_by(DimRole.role_id))
    roles = result.scalars().all()
    data = [get_rbac_service().serialize_role(role) for role in roles]
    return success_response(data=data, message="获取可分配角色成功")


@router.get("/roles")
async def list_admin_roles(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole).order_by(DimRole.role_id))
    roles = result.scalars().all()
    data = [get_rbac_service().serialize_role(role) for role in roles]
    return success_response(data=data, message="获取角色列表成功")


@router.get("/roles/{role_id}")
async def get_admin_role(
    role_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return success_response(data=get_rbac_service().serialize_role(role), message="获取角色详情成功")


@router.post("/roles")
async def create_admin_role(
    role_data: RoleCreate,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    role_code = (role_data.role_code or role_data.name).strip().lower()
    existing = await db.execute(
        select(DimRole).where((DimRole.role_code == role_code) | (DimRole.role_name == role_data.name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role already exists")

    role = DimRole(
        role_code=role_code,
        role_name=role_data.name,
        description=role_data.description,
        permissions=json.dumps(role_data.permissions, ensure_ascii=False),
        is_active=True,
        is_system=False,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="create_role",
        resource="role",
        resource_id=str(role.role_id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"role_code": role.role_code, "role_name": role.role_name},
    )
    return success_response(data=get_rbac_service().serialize_role(role), message="创建角色成功")


@router.put("/roles/{role_id}")
async def update_admin_role(
    role_id: int,
    role_update: RoleUpdate,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role_update.description is not None:
        role.description = role_update.description
    if role_update.role_code is not None:
        role.role_code = role_update.role_code.strip().lower()
    if role_update.permissions is not None:
        role.permissions = json.dumps(role_update.permissions, ensure_ascii=False)

    await db.commit()
    await db.refresh(role)

    await audit_service.log_action(
        user_id=current_user.user_id,
        action="update_role",
        resource="role",
        resource_id=str(role.role_id),
        ip_address="127.0.0.1",
        user_agent="Unknown",
        details={"role_code": role.role_code},
    )
    return success_response(data=get_rbac_service().serialize_role(role), message="更新角色成功")


@router.delete("/roles/{role_id}")
async def delete_admin_role(
    role_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole).where(DimRole.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="System role cannot be deleted")

    count_result = await db.execute(
        select(func.count(user_roles.c.user_id)).where(user_roles.c.role_id == role_id)
    )
    if (count_result.scalar() or 0) > 0:
        raise HTTPException(status_code=400, detail="Role is assigned to users")

    await db.delete(role)
    await db.commit()
    return success_response(data={"role_id": role_id}, message="删除角色成功")


@router.get("/rbac/permission-usage")
async def get_permission_usage(
    permission_id: str,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(DimRole))
    roles = result.scalars().all()
    matched = [
        get_rbac_service().serialize_role(role)
        for role in roles
        if permission_id in get_rbac_service().serialize_role(role)["permissions"]
    ]
    return success_response(
        data={
            "permission_id": permission_id,
            "roles": matched,
            "roles_count": len(matched),
        },
        message="获取权限使用情况成功",
    )


@router.post("/rbac/check-permission")
async def check_permission_assignment(
    payload: dict,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    user_id = payload.get("user_id")
    permission_id = payload.get("permission_id")
    if not user_id or not permission_id:
        raise HTTPException(status_code=400, detail="user_id and permission_id are required")

    result = await db.execute(
        select(DimUser).options(selectinload(DimUser.roles)).where(DimUser.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    has_permission = permission_id in get_rbac_service().resolve_permissions_from_roles(getattr(user, "roles", []))
    if get_rbac_service().is_admin(user):
        has_permission = True
    return success_response(
        data={
            "user_id": user_id,
            "permission_id": permission_id,
            "has_permission": has_permission,
        },
        message="权限校验成功",
    )
