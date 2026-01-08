"""
权限管理API路由
提供权限树查询功能

v4.20.0: 系统管理模块API实现
"""

from fastapi import APIRouter, Depends
from backend.routers.auth import get_current_user
from backend.schemas.permission import PermissionTreeNode, PermissionTreeResponse
from backend.services.permission_service import get_permission_service
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/permissions", tags=["权限管理"])


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
