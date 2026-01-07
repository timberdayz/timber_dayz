"""
账号管理相关的Pydantic Schemas
用于账号CRUD、导入导出、统计等API
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class CapabilitiesModel(BaseModel):
    """能力配置模型"""
    orders: bool = Field(default=True, description="订单数据")
    products: bool = Field(default=True, description="商品数据")
    services: bool = Field(default=True, description="客服数据")
    analytics: bool = Field(default=True, description="流量数据")
    finance: bool = Field(default=True, description="财务数据")
    inventory: bool = Field(default=True, description="库存数据")


class AccountCreate(BaseModel):
    """创建账号请求模型"""
    account_id: str = Field(..., description="账号唯一标识")
    parent_account: Optional[str] = Field(None, description="主账号（多店铺共用时填写）")
    platform: str = Field(..., description="平台代码")
    account_alias: Optional[str] = Field(None, description="账号别名（用于关联导出数据中的自定义名称）")
    store_name: str = Field(..., description="店铺名称")
    shop_type: Optional[str] = Field(None, description="店铺类型: local/global")
    shop_region: Optional[str] = Field(None, description="店铺区域: SG/MY/GLOBAL等")
    username: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码（明文，后端加密）")
    login_url: Optional[str] = Field(None, description="登录URL")
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")
    region: str = Field(default="CN", description="账号注册地区")
    currency: str = Field(default="CNY", description="主货币")
    capabilities: CapabilitiesModel = Field(default_factory=CapabilitiesModel, description="能力配置")
    enabled: bool = Field(default=True, description="是否启用")
    proxy_required: bool = Field(default=False, description="是否需要代理")
    notes: Optional[str] = Field(None, description="备注")


class AccountUpdate(BaseModel):
    """更新账号请求模型（所有字段可选）"""
    parent_account: Optional[str] = None
    platform: Optional[str] = None
    account_alias: Optional[str] = None
    store_name: Optional[str] = None
    shop_type: Optional[str] = None
    shop_region: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # 如果提供则重新加密
    login_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    currency: Optional[str] = None
    capabilities: Optional[CapabilitiesModel] = None
    enabled: Optional[bool] = None
    proxy_required: Optional[bool] = None
    notes: Optional[str] = None


class AccountResponse(BaseModel):
    """账号响应模型（不含密码）"""
    id: int
    account_id: str
    parent_account: Optional[str]
    platform: str
    account_alias: Optional[str]
    store_name: str
    shop_type: Optional[str]
    shop_region: Optional[str]
    username: str
    # 密码不返回！
    login_url: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    region: str
    currency: str
    capabilities: dict
    enabled: bool
    proxy_required: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    updated_by: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


class AccountStats(BaseModel):
    """账号统计模型"""
    total: int = Field(description="总账号数")
    active: int = Field(description="活跃账号数")
    inactive: int = Field(description="禁用账号数")
    platforms: int = Field(description="支持平台数")
    platform_breakdown: dict = Field(description="各平台账号数")


class AccountImportResponse(BaseModel):
    """账号导入响应（从local_accounts.py导入）"""
    message: str = Field(description="导入消息")
    imported_count: int = Field(description="成功导入数量")
    skipped_count: int = Field(description="跳过数量")
    failed_count: int = Field(description="失败数量")
    details: list = Field(default_factory=list, description="详细信息")

