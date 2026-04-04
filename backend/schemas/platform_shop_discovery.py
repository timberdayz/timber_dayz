from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlatformShopDiscoveryResponse(BaseModel):
    id: int
    platform: str
    main_account_id: str
    detected_store_name: Optional[str]
    detected_platform_shop_id: Optional[str]
    detected_region: Optional[str]
    candidate_shop_account_ids: Optional[list[str]]
    status: str
    raw_payload: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlatformShopDiscoveryConfirmRequest(BaseModel):
    shop_account_id: str = Field(..., description="确认归属的店铺账号ID")


class PlatformShopDiscoveryCreateShopAccountRequest(BaseModel):
    shop_account_id: str = Field(..., description="新店铺账号ID")
    store_name: str = Field(..., description="店铺名称")
    shop_region: Optional[str] = Field(default=None, description="店铺区域")
    shop_type: Optional[str] = Field(default=None, description="店铺类型")
    notes: Optional[str] = Field(default=None, description="备注")
