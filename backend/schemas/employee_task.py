from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EmployeeTaskParticipantPayload(BaseModel):
    user_id: int
    participant_role: str


class EmployeeTaskLogPayload(BaseModel):
    id: int
    actor_user_id: int | None = None
    action: str
    message: str
    details_json: dict[str, Any] = {}
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeTaskPayload(BaseModel):
    task_id: str
    task_type: str
    task_category: str
    title: str
    description: str | None = None
    status: str
    priority: str
    owner_user_id: int
    source_type: str
    source_module: str
    source_record_type: str | None = None
    source_record_id: str | None = None
    cc_user_ids: list[int] = []
    collaborator_user_ids: list[int] = []
    completion_schema: dict[str, Any] | None = None
    completion_payload: dict[str, Any] | None = None
    result_status: str | None = None
    result_comment: str | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    closed_at: datetime | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeTaskDetailPayload(EmployeeTaskPayload):
    timeline: list[EmployeeTaskLogPayload] = []


class EmployeeTaskSubmitRequest(BaseModel):
    completion_payload: dict[str, Any]
    result_comment: str | None = None
    requires_confirmation: bool = False
