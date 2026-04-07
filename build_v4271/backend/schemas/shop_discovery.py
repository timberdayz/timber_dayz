from typing import Literal, Optional

from pydantic import BaseModel, Field


class ShopDiscoveryRunRequest(BaseModel):
    mode: Literal["current_only"] = Field(
        default="current_only",
        description="店铺探测模式，P1 仅支持 current_only",
    )
    reuse_session: bool = Field(default=True, description="是否优先复用主账号会话")
    expected_region: Optional[str] = Field(default=None, description="期望区域")
    capture_evidence: bool = Field(default=True, description="是否保存截图和证据")


class ShopDiscoveryFieldSource(BaseModel):
    platform_shop_id: Optional[str] = None
    store_name: Optional[str] = None
    region: Optional[str] = None


class ShopDiscoveryPayload(BaseModel):
    detected_store_name: Optional[str] = None
    detected_platform_shop_id: Optional[str] = None
    detected_region: Optional[str] = None
    current_url: Optional[str] = None
    source: ShopDiscoveryFieldSource = Field(default_factory=ShopDiscoveryFieldSource)
    confidence: float = 0.0


class ShopDiscoveryMatchPayload(BaseModel):
    status: str
    shop_account_id: Optional[str] = None
    candidate_count: int = 0


class ShopDiscoveryEvidencePayload(BaseModel):
    screenshot_path: Optional[str] = None


class ShopDiscoveryRunResponse(BaseModel):
    success: bool
    platform: str
    main_account_id: str
    mode: str
    discovery: ShopDiscoveryPayload
    match: ShopDiscoveryMatchPayload
    evidence: ShopDiscoveryEvidencePayload = Field(default_factory=ShopDiscoveryEvidencePayload)
