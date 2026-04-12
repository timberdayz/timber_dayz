from __future__ import annotations

from pydantic import BaseModel


class TrainingSummaryResponse(BaseModel):
    total_count: int
    pending_count: int
    studying_count: int
    pending_exam_count: int
    passed_count: int
    failed_count: int
    overdue_count: int


class TrainingProgramResponse(BaseModel):
    program_id: str
    name: str
    category: str
    target_role: str
    external_platform: str
    completion_rule: str
    learning_url: str | None = None
    exam_url: str | None = None
    materials_url: str | None = None
    external_course_id: str | None = None
    external_exam_id: str | None = None
    status: str


class TrainingProgramCreateRequest(BaseModel):
    name: str
    category: str
    target_role: str
    external_platform: str
    completion_rule: str
    learning_url: str | None = None
    exam_url: str | None = None
    materials_url: str | None = None
    external_course_id: str | None = None
    external_exam_id: str | None = None
    status: str


class TrainingAssignmentResponse(BaseModel):
    assignment_id: str
    employee_name: str
    employee_code: str
    department: str
    role_name: str
    program_name: str
    learning_status: str
    current_status: str
    due_date: str
    supervisor_name: str
    task_id: str | None = None
    note: str = ""
    exam_score: int | None = None
    updated_at: str | None = None


class TrainingAssignmentCreateRequest(BaseModel):
    employee_name: str
    employee_code: str
    department: str
    role_name: str
    program_name: str
    learning_status: str
    current_status: str
    due_date: str
    supervisor_name: str
    note: str = ""


class TrainingResultResponse(BaseModel):
    assignment_id: str
    employee_name: str
    employee_code: str
    program_name: str
    exam_score: int | None = None
    is_passed: bool
    current_status: str
    updated_at: str
    note: str = ""


class TrainingResultUpdateRequest(BaseModel):
    exam_score: int | None = None
    current_status: str
    note: str = ""


class TrainingOverviewResponse(BaseModel):
    module_name: str
    summary: TrainingSummaryResponse
    items: list[TrainingAssignmentResponse]


class TrainingProgramListResponse(BaseModel):
    items: list[TrainingProgramResponse]


class TrainingAssignmentListResponse(BaseModel):
    items: list[TrainingAssignmentResponse]


class TrainingResultListResponse(BaseModel):
    items: list[TrainingResultResponse]


class MyTrainingOverviewResponse(BaseModel):
    employee_name: str
    summary: TrainingSummaryResponse
    items: list[TrainingAssignmentResponse]


class TrainingFeishuConfigResponse(BaseModel):
    provider_code: str
    app_id: str
    tenant_key: str | None = None
    base_url: str | None = None
    is_enabled: bool
    has_secret: bool


class TrainingFeishuConfigUpdateRequest(BaseModel):
    app_id: str
    app_secret: str | None = None
    tenant_key: str | None = None
    base_url: str | None = None
    is_enabled: bool = False


class TrainingProgramFeishuBindingRequest(BaseModel):
    course_id: str | None = None
    exam_id: str | None = None


class TrainingFeishuSyncItemRequest(BaseModel):
    employee_code: str
    exam_score: int | None = None
    is_passed: bool = False
    note: str = ""


class TrainingFeishuSyncRequest(BaseModel):
    program_id: str
    results: list[TrainingFeishuSyncItemRequest]
