from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ShopAccountCreate(BaseModel):
    platform: str = Field(..., description="平台代码")
    shop_account_id: str = Field(..., description="店铺账号ID")
    main_account_id: str = Field(..., description="归属主账号ID")
    store_name: str = Field(..., description="店铺名称")
    platform_shop_id: Optional[str] = Field(None, description="平台店铺ID")
    shop_region: Optional[str] = Field(None, description="店铺区域")
    shop_type: Optional[str] = Field(None, description="店铺类型")
    capabilities: Optional[dict[str, bool]] = Field(None, description="店铺数据域能力配置")
    enabled: bool = Field(default=True, description="是否启用")
    notes: Optional[str] = Field(None, description="备注")


class ShopAccountUpdate(BaseModel):
    store_name: Optional[str] = None
    platform_shop_id: Optional[str] = None
    platform_shop_id_status: Optional[str] = None
    shop_region: Optional[str] = None
    shop_type: Optional[str] = None
    capabilities: Optional[dict[str, bool]] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class ShopAccountResponse(BaseModel):
    id: int
    platform: str
    shop_account_id: str
    main_account_id: str
    account_alias: Optional[str] = None
    alias_count: int = 0
    capabilities: dict = Field(default_factory=dict)
    store_name: str
    platform_shop_id: Optional[str]
    platform_shop_id_status: str
    shop_region: Optional[str]
    shop_type: Optional[str]
    enabled: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
