from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MainAccountCreate(BaseModel):
    platform: str = Field(..., description="平台代码")
    main_account_id: str = Field(..., description="主账号ID")
    main_account_name: Optional[str] = Field(None, description="主账号名称")
    username: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码")
    login_url: Optional[str] = Field(None, description="登录URL")
    enabled: bool = Field(default=True, description="是否启用")
    notes: Optional[str] = Field(None, description="备注")


class MainAccountUpdate(BaseModel):
    main_account_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    login_url: Optional[str] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class MainAccountResponse(BaseModel):
    id: int
    platform: str
    main_account_id: str
    main_account_name: Optional[str]
    username: str
    login_url: Optional[str]
    enabled: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
