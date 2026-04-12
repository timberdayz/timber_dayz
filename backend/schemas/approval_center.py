from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ApprovalStepPayload(BaseModel):
    step_order: int
    approver_type: str
    approver_user_id: int | None = None
    status: str
    acted_at: datetime | None = None


class ApprovalActionLogPayload(BaseModel):
    action_type: str
    actor_user_id: int
    comment: str | None = None
    created_at: datetime | None = None


class ApprovalInstancePayload(BaseModel):
    approval_id: str
    template_code: str
    applicant_user_id: int
    business_key: str | None = None
    status: str
    current_step: int | None = None
    submitted_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[ApprovalStepPayload] = []
    timeline: list[ApprovalActionLogPayload] = []


class SubmitApprovalRequest(BaseModel):
    template_code: str
    business_key: str | None = None
    form_payload: dict[str, Any]
    approver_user_id: int


class ApprovalActionRequest(BaseModel):
    comment: str | None = None
