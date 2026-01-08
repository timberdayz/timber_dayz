"""
权限管理相关的Pydantic Schemas
用于权限列表和权限树API

v4.20.0: 系统管理模块API实现
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PermissionResponse(BaseModel):
    """权限响应模型（权限代码、名称、描述、分类）"""
    id: str = Field(description="权限代码（唯一标识）")
    name: str = Field(description="权限名称")
    description: str = Field(description="权限描述")
    resource: str = Field(description="资源类型（模块）")
    action: Optional[str] = Field(None, description="操作类型（read/write/all）")
    category: Optional[str] = Field(None, description="权限分类（模块分组）")
    
    model_config = ConfigDict(from_attributes=True)


class PermissionTreeNode(BaseModel):
    """权限树节点模型"""
    id: str = Field(description="权限代码（唯一标识）")
    name: str = Field(description="权限名称")
    description: str = Field(description="权限描述")
    resource: str = Field(description="资源类型（模块）")
    action: Optional[str] = Field(None, description="操作类型（read/write/all）")
    category: Optional[str] = Field(None, description="权限分类（模块分组）")
    children: Optional[List["PermissionTreeNode"]] = Field(None, description="子节点列表（树形结构）")
    
    model_config = ConfigDict(from_attributes=True)


class PermissionTreeResponse(BaseModel):
    """权限树响应模型"""
    success: bool = Field(default=True, description="请求是否成功")
    data: List[PermissionTreeNode] = Field(description="权限树根节点列表（按模块分组）")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")


class PermissionListResponse(BaseModel):
    """权限列表响应模型"""
    success: bool = Field(default=True, description="请求是否成功")
    data: List[PermissionResponse] = Field(description="权限列表")
    total: int = Field(description="权限总数")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间")
