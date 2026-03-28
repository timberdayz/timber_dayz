from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TaskCenterTaskPayload(BaseModel):
    task_id: str
    task_family: str
    task_type: str
    status: str
    trigger_source: Optional[str] = None
    priority: int
    runner_kind: Optional[str] = None
    external_runner_id: Optional[str] = None
    platform_code: Optional[str] = None
    account_id: Optional[str] = None
    source_file_id: Optional[int] = None
    source_table_name: Optional[str] = None
    current_step: Optional[str] = None
    progress_percent: float = 0.0
    details_json: dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class TaskCenterLogPayload(BaseModel):
    id: int
    task_pk: int
    level: str
    event_type: str
    message: str
    details_json: dict[str, Any] = {}
    created_at: Optional[str] = None


class TaskCenterListResponse(BaseModel):
    items: list[TaskCenterTaskPayload]
    total: int
    page: int
    page_size: int


class TaskCenterLogsResponse(BaseModel):
    items: list[TaskCenterLogPayload]
