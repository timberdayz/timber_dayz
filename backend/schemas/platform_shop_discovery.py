from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


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
