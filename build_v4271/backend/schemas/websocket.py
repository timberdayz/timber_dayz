"""
WebSocket 消息 API 契约 (Contract-First)
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CollectionWebSocketMessage(BaseModel):
    """采集 WebSocket 消息格式"""

    type: str
    task_id: str
    data: Dict


class NotificationWebSocketMessage(BaseModel):
    """通知 WebSocket 消息格式"""

    type: str = Field(..., description="消息类型")
    data: Optional[Dict] = Field(None, description="消息数据")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed_types = ["ping", "pong", "notification"]
        if v not in allowed_types:
            raise ValueError(
                f"Invalid message type: {v}. Allowed: {allowed_types}"
            )
        return v


class NotificationMessage(BaseModel):
    """通知消息格式"""

    notification_id: int
    recipient_id: int
    notification_type: str
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=1000)
    extra_data: Optional[Dict] = None
    related_user_id: Optional[int] = None
    created_at: str
