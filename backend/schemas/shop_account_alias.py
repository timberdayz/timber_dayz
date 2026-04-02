from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ShopAccountAliasCreate(BaseModel):
    shop_account_id: int = Field(..., description="归属店铺账号主键")
    platform: str = Field(..., description="平台代码")
    alias_value: str = Field(..., description="别名原值")
    alias_type: Optional[str] = Field(None, description="别名类型")
    source: Optional[str] = Field(None, description="来源")
    is_primary: bool = Field(default=False, description="是否主别名")
    is_active: bool = Field(default=True, description="是否启用")


class ShopAccountAliasResponse(BaseModel):
    id: int
    shop_account_id: int
    platform: str
    alias_value: str
    alias_normalized: str
    alias_type: Optional[str]
    source: Optional[str]
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
