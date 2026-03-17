"""
Metabase 代理 API 契约 (Contract-First)
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class EmbeddingTokenRequest(BaseModel):
    """嵌入token请求"""

    dashboard_id: int
    filters: Optional[Dict[str, Any]] = None


class DashboardEmbedUrlRequest(BaseModel):
    """Dashboard嵌入URL请求"""

    dashboard_id: int
    filters: Optional[Dict[str, Any]] = None
    granularity: Optional[str] = "daily"
