"""
账号管理相关的 Pydantic Schemas
用于账号 CRUD、批量创建、统计以及未匹配别名提示。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CapabilitiesModel(BaseModel):
    orders: bool = Field(default=True, description="订单数据")
    products: bool = Field(default=True, description="商品数据")
    services: bool = Field(default=True, description="客服数据")
    analytics: bool = Field(default=True, description="流量数据")
    finance: bool = Field(default=True, description="财务数据")
    inventory: bool = Field(default=True, description="库存数据")


class AccountCreate(BaseModel):
    account_id: str = Field(..., description="账号唯一标识")
    parent_account: Optional[str] = Field(None, description="主账号")
    platform: str = Field(..., description="平台代码")
    account_alias: Optional[str] = Field(None, description="账号别名")
    store_name: str = Field(..., description="店铺名称")
    shop_type: Optional[str] = Field(None, description="店铺类型")
    shop_region: Optional[str] = Field(None, description="店铺区域")
    shop_id: Optional[str] = Field(None, description="标准店铺ID")
    username: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码")
    login_url: Optional[str] = Field(None, description="登录 URL")
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")
    region: str = Field(default="CN", description="账号注册地区")
    currency: str = Field(default="CNY", description="主货币")
    capabilities: CapabilitiesModel = Field(default_factory=CapabilitiesModel, description="能力配置")
    enabled: bool = Field(default=True, description="是否启用")
    proxy_required: bool = Field(default=False, description="是否需要代理")
    notes: Optional[str] = Field(None, description="备注")


class AccountUpdate(BaseModel):
    parent_account: Optional[str] = None
    platform: Optional[str] = None
    account_alias: Optional[str] = None
    store_name: Optional[str] = None
    shop_type: Optional[str] = None
    shop_region: Optional[str] = None
    shop_id: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
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
    id: int
    account_id: str
    parent_account: Optional[str]
    platform: str
    account_alias: Optional[str]
    store_name: str
    shop_type: Optional[str]
    shop_region: Optional[str]
    shop_id: Optional[str]
    username: str
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
    total: int = Field(description="总账号数")
    active: int = Field(description="活跃账号数")
    inactive: int = Field(description="禁用账号数")
    platforms: int = Field(description="支持平台数")
    platform_breakdown: dict = Field(description="各平台账号数")


class BatchCreateRequest(BaseModel):
    parent_account: str = Field(..., description="主账号")
    platform: str = Field(..., description="平台代码")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    shops: list = Field(..., description="店铺列表")


class UnmatchedShopAliasItem(BaseModel):
    platform: str = Field(description="平台代码")
    site: Optional[str] = Field(default=None, description="站点")
    store_label_raw: str = Field(description="原始店铺别名")
    row_count: int = Field(description="命中行数")
    order_count: int = Field(description="订单数")
    paid_amount: float = Field(description="支付金额汇总")


class UnmatchedShopAliasResponse(BaseModel):
    items: list[UnmatchedShopAliasItem] = Field(default_factory=list, description="未匹配店铺别名列表")
    count: int = Field(default=0, description="未匹配条数")
