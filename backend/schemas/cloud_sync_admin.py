from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CloudSyncWorkerHealth(BaseModel):
    status: str
    worker_id: str | None = None
    poll_interval_seconds: float | None = None
    last_error: str | None = None
    last_heartbeat_at: str | None = None


class CloudSyncDependencyHealth(BaseModel):
    status: str
    last_checked_at: str | None = None
    error: str | None = None


class CloudSyncQueueSummary(BaseModel):
    pending: int = 0
    running: int = 0
    retry_waiting: int = 0
    failed: int = 0
    partial_success: int = 0
    completed_recent_24h: int = 0
    oldest_pending_age_seconds: int | None = None


class CloudSyncHealthSummary(BaseModel):
    worker: CloudSyncWorkerHealth
    tunnel: CloudSyncDependencyHealth
    cloud_db: CloudSyncDependencyHealth
    queue: CloudSyncQueueSummary


class CloudSyncCheckpointState(BaseModel):
    table_schema: str | None = None
    last_source_id: int | None = None
    last_ingest_timestamp: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class CloudSyncLatestTaskState(BaseModel):
    job_id: str | None = None
    status: str | None = None
    attempt_count: int | None = None
    trigger_source: str | None = None
    source_file_id: int | None = None
    claimed_by: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    last_attempt_started_at: str | None = None
    last_attempt_finished_at: str | None = None
    projection_status: str | None = None
    last_error: str | None = None
    error_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None


class CloudSyncProjectionState(BaseModel):
    preset: str | None = None
    status: str | None = None


class CloudSyncTableStateRow(BaseModel):
    source_table_name: str
    platform_code: str | None = None
    data_domain: str | None = None
    sub_domain: str | None = None
    checkpoint: CloudSyncCheckpointState
    latest_task: CloudSyncLatestTaskState
    projection: CloudSyncProjectionState
    last_success_at: str | None = None
    latest_error: str | None = None


class CloudSyncTaskRow(BaseModel):
    job_id: str
    status: str
    source_table_name: str
    attempt_count: int = 0
    trigger_source: str | None = None
    source_file_id: int | None = None
    claimed_by: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    last_attempt_started_at: str | None = None
    last_attempt_finished_at: str | None = None
    projection_status: str | None = None
    projection_preset: str | None = None
    last_error: str | None = None
    error_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    metadata: dict[str, Any] = {}


class CloudSyncCommandResponse(BaseModel):
    job_id: str | None = None
    status: str
    source_table_name: str | None = None
    detail: str | None = None
    metadata: dict[str, Any] = {}

    model_config = ConfigDict(extra="allow")
