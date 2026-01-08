"""
权限列表API路由
提供系统预定义权限列表查询功能

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Query
from typing import Optional
from backend.routers.auth import get_current_user
from backend.schemas.permission import PermissionResponse, PermissionListResponse, PermissionTreeResponse, PermissionTreeNode
from backend.services.permission_service import get_permission_service
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/permissions", tags=["权限管理"])


@router.get("", response_model=PermissionListResponse)
async def get_permissions(
    category: Optional[str] = Query(None, description="权限分类（模块分组）"),
    current_user = Depends(get_current_user)
):
    """
    获取权限列表（系统预定义权限列表）
    
    返回所有系统预定义权限，支持按分类筛选
    注意：权限分配由角色管理 API 完成（通过 `/api/roles` 更新 `DimRole.permissions` 字段）
    """
    try:
        service = get_permission_service()
        permissions_data = service.get_permissions_by_category(category)
        
        # 转换为PermissionResponse模型
        permissions = [
            PermissionResponse(
                id=perm["id"],
                name=perm["name"],
                description=perm["description"],
                resource=perm["resource"],
                action=perm.get("action"),
                category=perm.get("category")
            )
            for perm in permissions_data
        ]
        
        return PermissionListResponse(
            success=True,
            data=permissions,
            total=len(permissions),
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"获取权限列表失败: {e}", exc_info=True)
        return PermissionListResponse(
            success=False,
            data=[],
            total=0,
            timestamp=datetime.now()
        )


@router.get("/tree", response_model=PermissionTreeResponse)
async def get_permission_tree(
    current_user = Depends(get_current_user)
):
    """
    获取权限树（层级结构）
    
    返回按模块分组的权限树，支持前端权限管理界面展示
    """
    try:
        service = get_permission_service()
        tree_data = service.build_permission_tree()
        
        # 转换为PermissionTreeNode模型
        def convert_to_node(data: dict) -> PermissionTreeNode:
            children = None
            if data.get("children"):
                children = [convert_to_node(child) for child in data["children"]]
            
            return PermissionTreeNode(
                id=data["id"],
                name=data["name"],
                description=data["description"],
                resource=data["resource"],
                action=data.get("action"),
                category=data.get("category"),
                children=children
            )
        
        tree_nodes = [convert_to_node(node) for node in tree_data]
        
        return PermissionTreeResponse(
            success=True,
            data=tree_nodes,
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"获取权限树失败: {e}", exc_info=True)
        return PermissionTreeResponse(
            success=False,
            data=[],
            timestamp=datetime.now()
        )
