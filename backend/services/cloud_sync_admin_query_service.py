from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import socket
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import make_url

from backend.services.cloud_b_class_auto_sync_factory import get_current_checkpoint_scope_from_env
from backend.schemas.cloud_sync_admin import (
    CloudSyncCheckpointState,
    CloudSyncDependencyHealth,
    CloudSyncHealthSummary,
    CloudSyncHistoryRow,
    CloudSyncLifecycleState,
    CloudSyncLatestTaskState,
    CloudSyncOverviewSummary,
    CloudSyncProjectionState,
    CloudSyncQueueSummary,
    CloudSyncReceiveLogState,
    CloudSyncRuntimeSummary,
    CloudSyncSettings,
    CloudSyncTableStateRow,
    CloudSyncTaskRow,
    CloudSyncWorkerHealth,
)
from modules.core.db import (
    CatalogFile,
    CloudBClassSyncCheckpoint,
    CloudBClassSyncTask,
    CloudSyncReceiveLog,
    RefreshQueueTask,
    SystemConfig,
    TaskCenterTask,
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sanitize_error_text(value: str | None) -> str | None:
    if not value:
        return value

    sanitized = re.sub(r'://([^:/\s]+):([^@/\s]+)@', r'://\1:***@', value)
    sanitized = re.sub(r'(?i)\b(password|secret|token)=([^\s&]+)', r'\1=***', sanitized)
    return sanitized


def _probe_tcp_target(host: str, port: int, timeout_seconds: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, None
    except Exception as exc:
        return False, _sanitize_error_text(str(exc))


def _classify_cloud_sync_error(raw_error: str | None) -> tuple[str | None, str | None, str | None]:
    if not raw_error:
        return None, None, None

    lowered = raw_error.lower()
    if "stale_running_recovered_on_startup" in lowered:
        return (
            "stale_running_detected",
            "检测到历史遗留运行任务，系统已在启动时回收。",
            "刷新页面后确认任务已回到待处理状态。",
        )
    if "could not receive data from server" in lowered or "software caused connection abort" in lowered:
        return (
            "local_db_connection_aborted",
            "本地数据库连接曾中断，任务状态未正常收尾。",
            "确认本地后端与数据库稳定后，重试异常任务。",
        )
    if "connection refused" in lowered or "timed out" in lowered:
        return (
            "cloud_db_unreachable",
            "云端数据库当前不可达。",
            "检查 SSH tunnel 和 CLOUD_DATABASE_URL 配置。",
        )
    return (
        "unknown_runtime_error",
        "Cloud Sync worker 出现未分类异常。",
        "查看后端日志并按需重试异常任务。",
    )


class CloudSyncAdminQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _parse_bool(value: str | None, default: bool = True) -> bool:
        if value is None:
            return default
        return str(value).lower() in {"1", "true", "yes", "on"}

    async def _auto_sync_enabled(self) -> bool:
        try:
            result = await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == "cloud_sync_auto_sync_enabled")
            )
            record = result.scalars().one_or_none()
            if record is not None:
                return self._parse_bool(record.config_value, default=True)
        except Exception:
            pass

        return self._parse_bool(os.getenv("CLOUD_SYNC_AUTO_SYNC_ENABLED", "true"), default=True)

    async def get_health_summary(self, runtime_health: dict | None = None) -> dict:
        current_scope = self._current_checkpoint_scope()
        tasks = (await self.db.execute(select(CloudBClassSyncTask))).scalars().all()
        scoped_tasks = [task for task in tasks if self._task_matches_scope(task, current_scope)]
        now = datetime.now(timezone.utc)
        stale_running = [
            task
            for task in scoped_tasks
            if task.status == "running"
            and task.lease_expires_at is not None
            and _as_utc(task.lease_expires_at) is not None
            and _as_utc(task.lease_expires_at) < now
        ]
        oldest_pending = min(
            (
                int((now - _as_utc(task.created_at)).total_seconds())
                for task in scoped_tasks
                if task.status in {"pending", "retry_waiting"} and task.created_at is not None
            ),
            default=None,
        )
        completed_recent_24h = sum(
            1
            for task in scoped_tasks
            if task.status == "completed"
            and task.finished_at is not None
            and _as_utc(task.finished_at) >= now - timedelta(hours=24)
        )

        cloud_db_health = self._probe_cloud_db_health()
        tunnel_health = self._probe_tunnel_health(cloud_db_health)
        worker_health = self._resolve_worker_health(runtime_health)

        payload = CloudSyncHealthSummary(
            worker=CloudSyncWorkerHealth(**worker_health),
            tunnel=CloudSyncDependencyHealth(**tunnel_health),
            cloud_db=CloudSyncDependencyHealth(**cloud_db_health),
            queue=CloudSyncQueueSummary(
                pending=sum(1 for task in tasks if task.status == "pending"),
                running=sum(
                    1
                    for task in scoped_tasks
                    if task.status == "running"
                    and (
                        task.lease_expires_at is None
                        or _as_utc(task.lease_expires_at) is None
                        or _as_utc(task.lease_expires_at) >= now
                    )
                ),
                stale_running=len(stale_running),
                retry_waiting=sum(1 for task in scoped_tasks if task.status == "retry_waiting"),
                failed=sum(1 for task in scoped_tasks if task.status == "failed"),
                partial_success=sum(1 for task in scoped_tasks if task.status == "partial_success"),
                completed_recent_24h=completed_recent_24h,
                oldest_pending_age_seconds=oldest_pending,
            ),
        )
        return payload.model_dump()

    async def list_tasks(self, *, limit: int = 100) -> list[dict]:
        stmt = select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit)
        tasks = (await self.db.execute(stmt)).scalars().all()
        file_context = await self._load_file_context([task.source_file_id for task in tasks if task.source_file_id is not None])
        table_context = await self._load_table_context([task.source_table_name for task in tasks if task.source_table_name])
        return [
            self._serialize_task(
                task,
                file_context=file_context.get(task.source_file_id),
                table_context=table_context.get(task.source_table_name),
            ).model_dump()
            for task in tasks
        ]

    async def get_task(self, job_id: str) -> dict | None:
        stmt = select(CloudBClassSyncTask).where(CloudBClassSyncTask.job_id == job_id)
        task = (await self.db.execute(stmt)).scalars().one_or_none()
        if task is None:
            return None
        file_context = await self._load_file_context([task.source_file_id] if task.source_file_id is not None else [])
        table_context = await self._load_table_context([task.source_table_name] if task.source_table_name else [])
        return self._serialize_task(
            task,
            file_context=file_context.get(task.source_file_id),
            table_context=table_context.get(task.source_table_name),
        ).model_dump()

    async def list_table_states(self) -> list[dict]:
        current_scope = self._current_checkpoint_scope()
        checkpoints = (
            await self.db.execute(select(CloudBClassSyncCheckpoint).order_by(CloudBClassSyncCheckpoint.id.desc()))
        ).scalars().all()
        tasks = (
            await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()))
        ).scalars().all()

        checkpoint_by_table = {}
        for checkpoint in checkpoints:
            if checkpoint.table_schema != current_scope:
                continue
            checkpoint_by_table.setdefault(checkpoint.table_name, checkpoint)

        latest_task_by_table = {}
        for task in tasks:
            if not self._task_matches_scope(task, current_scope):
                continue
            latest_task_by_table.setdefault(task.source_table_name, task)

        receive_by_table = await self._load_latest_receive_by_table()
        refresh_by_table = await self._load_latest_refresh_by_table()
        table_names = sorted(
            set(checkpoint_by_table)
            | set(latest_task_by_table)
            | set(receive_by_table)
            | set(refresh_by_table)
        )
        file_context = await self._load_file_context(
            [
                latest_task.source_file_id
                for latest_task in latest_task_by_table.values()
                if getattr(latest_task, "source_file_id", None) is not None
            ]
        )
        rows = []
        for table_name in table_names:
            checkpoint = checkpoint_by_table.get(table_name)
            latest_task = latest_task_by_table.get(table_name)
            file_ctx = file_context.get(getattr(latest_task, "source_file_id", None))
            table_ctx = {
                "receive": receive_by_table.get(table_name),
                "refresh": refresh_by_table.get(table_name),
            }
            row = CloudSyncTableStateRow(
                source_table_name=table_name,
                platform_code=getattr(latest_task, "platform_code", None),
                data_domain=getattr(latest_task, "data_domain", None),
                sub_domain=getattr(latest_task, "sub_domain", None),
                checkpoint=CloudSyncCheckpointState(
                    table_schema=getattr(checkpoint, "table_schema", None),
                    last_source_id=getattr(checkpoint, "last_source_id", None),
                    last_ingest_timestamp=_iso(getattr(checkpoint, "last_ingest_timestamp", None)),
                    last_status=getattr(checkpoint, "last_status", None),
                    last_error=_sanitize_error_text(getattr(checkpoint, "last_error", None)),
                ),
                latest_task=self._serialize_task_state(latest_task),
                projection=CloudSyncProjectionState(
                    preset=getattr(latest_task, "projection_preset", None),
                    status=getattr(latest_task, "projection_status", None),
                ),
                lifecycle=self._build_lifecycle_state(latest_task, file_ctx, table_ctx),
                receive_log=self._build_receive_log_state(table_ctx.get("receive")),
                last_success_at=_iso(getattr(latest_task, "finished_at", None))
                if getattr(latest_task, "status", None) == "completed"
                else None,
                latest_error=_sanitize_error_text(
                    getattr(latest_task, "last_error", None) or getattr(checkpoint, "last_error", None)
                ),
            )
            rows.append(row.model_dump())
        return rows

    async def list_events(self, *, limit: int = 20) -> list[dict]:
        stmt = select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit)
        tasks = (await self.db.execute(stmt)).scalars().all()
        events = []
        for task in tasks:
            timestamp = task.last_attempt_finished_at or task.last_attempt_started_at or task.created_at
            events.append(
                {
                    "title": f"{task.source_table_name} {task.status}",
                    "status": task.status,
                    "job_id": task.job_id,
                    "source_table_name": task.source_table_name,
                    "timestamp": _iso(timestamp),
                    "last_error": _sanitize_error_text(task.last_error),
                }
            )
        return events

    async def get_overview_summary(self, runtime_health: dict | None = None) -> dict:
        current_scope = self._current_checkpoint_scope()
        tasks = (await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()))).scalars().all()
        scoped_tasks = [task for task in tasks if self._task_matches_scope(task, current_scope)]
        legacy_scope_tasks = [task for task in tasks if not self._task_matches_scope(task, current_scope)]
        now = datetime.now(timezone.utc)
        failed = sum(1 for task in scoped_tasks if task.status == "failed")
        partial_success = sum(1 for task in scoped_tasks if task.status == "partial_success")
        pending = sum(1 for task in scoped_tasks if task.status == "pending")
        stale_running = sum(
            1
            for task in scoped_tasks
            if task.status == "running"
            and task.lease_expires_at is not None
            and _as_utc(task.lease_expires_at) is not None
            and _as_utc(task.lease_expires_at) < now
        )
        running = sum(
            1
            for task in scoped_tasks
            if task.status == "running"
            and (
                task.lease_expires_at is None
                or _as_utc(task.lease_expires_at) is None
                or _as_utc(task.lease_expires_at) >= now
            )
        )
        retry_waiting = sum(1 for task in scoped_tasks if task.status == "retry_waiting")
        legacy_scope_exception_count = sum(
            1 for task in legacy_scope_tasks if task.status in {"failed", "partial_success", "running"}
        )
        latest_success = next((task for task in scoped_tasks if task.status == "completed" and task.finished_at is not None), None)
        pending_catalog_file_count, overdue_pending_catalog_file_count, processing_catalog_file_count = (
            await self._load_catalog_backlog_summary()
        )
        refresh_counts = await self._load_refresh_queue_counts()
        receive_by_table = await self._load_latest_receive_by_table()
        latest_receive_table_name = None
        latest_receive_at = None
        for table_name, receive_row in receive_by_table.items():
            created_at = _as_utc(getattr(receive_row, "created_at", None))
            if created_at is None:
                continue
            if latest_receive_at is None or created_at > latest_receive_at:
                latest_receive_at = created_at
                latest_receive_table_name = table_name
        latest_error_task = next((task for task in scoped_tasks if task.last_error), None)
        if latest_error_task is None and stale_running:
            latest_error_task = next(
                (
                    task
                    for task in scoped_tasks
                    if task.status == "running"
                    and task.lease_expires_at is not None
                    and _as_utc(task.lease_expires_at) is not None
                    and _as_utc(task.lease_expires_at) < now
                ),
                None,
            )
        error_code, error_summary, error_action_hint = _classify_cloud_sync_error(
            getattr(latest_error_task, "last_error", None)
            or (
                "stale_running_recovered_on_startup"
                if latest_error_task is not None and stale_running and not getattr(latest_error_task, "last_error", None)
                else None
            )
        )

        if failed or partial_success or stale_running:
            catch_up_status = "degraded"
        elif running:
            catch_up_status = "catching_up"
        elif pending or retry_waiting:
            catch_up_status = "backlog"
        else:
            catch_up_status = "up_to_date"

        worker_status = (runtime_health or {}).get("status", "not_started")
        if worker_status == "running":
            if stale_running:
                worker_status = "degraded"
            elif (runtime_health or {}).get("last_error"):
                worker_status = "error"

        payload = CloudSyncOverviewSummary(
            worker_status=worker_status,
            catch_up_status=catch_up_status,
            exception_task_count=failed + partial_success + stale_running,
            failed_task_count=failed,
            partial_success_task_count=partial_success,
            stale_running_task_count=stale_running,
            pending_task_count=pending,
            running_task_count=running,
            retry_waiting_task_count=retry_waiting,
            last_success_at=_iso(getattr(latest_success, "finished_at", None)),
            latest_error=_sanitize_error_text(getattr(latest_error_task, "last_error", None)),
            error_code=error_code,
            error_summary=error_summary,
            error_action_hint=error_action_hint,
            auto_sync_enabled=await self._auto_sync_enabled(),
            current_checkpoint_scope=current_scope,
            legacy_scope_exception_count=legacy_scope_exception_count,
            pending_catalog_file_count=pending_catalog_file_count,
            overdue_pending_catalog_file_count=overdue_pending_catalog_file_count,
            processing_catalog_file_count=processing_catalog_file_count,
            refresh_pending_task_count=refresh_counts["pending"],
            refresh_running_task_count=refresh_counts["running"],
            refresh_failed_task_count=refresh_counts["failed"],
            last_receive_at=_iso(latest_receive_at),
            last_receive_table_name=latest_receive_table_name,
        )
        return payload.model_dump()

    def _resolve_worker_health(self, runtime_health: dict | None) -> dict:
        if runtime_health is not None:
            return {
                "status": runtime_health.get("status", "not_started"),
                "worker_id": runtime_health.get("worker_id"),
                "poll_interval_seconds": runtime_health.get("poll_interval_seconds"),
                "last_error": _sanitize_error_text(runtime_health.get("last_error")),
                "last_heartbeat_at": runtime_health.get("last_heartbeat_at"),
                "last_runtime_heartbeat_at": runtime_health.get("last_runtime_heartbeat_at"),
                "last_recovered_at": runtime_health.get("last_recovered_at"),
                "last_recovered_count": int(runtime_health.get("last_recovered_count") or 0),
            }

        if self._worker_prereqs_missing():
            return {
                "status": "not_configured",
                "worker_id": None,
                "poll_interval_seconds": None,
                "last_error": None,
                "last_heartbeat_at": None,
                "last_runtime_heartbeat_at": None,
                "last_recovered_at": None,
                "last_recovered_count": 0,
            }

        return {
            "status": "not_started",
            "worker_id": None,
            "poll_interval_seconds": None,
            "last_error": None,
            "last_heartbeat_at": None,
            "last_runtime_heartbeat_at": None,
            "last_recovered_at": None,
            "last_recovered_count": 0,
        }

    def _worker_prereqs_missing(self) -> bool:
        worker_enabled = self._parse_bool(os.getenv("CLOUD_SYNC_WORKER_ENABLED"), default=False)
        collection_enabled = self._parse_bool(os.getenv("ENABLE_COLLECTION"), default=True)
        deployment_role = str(os.getenv("DEPLOYMENT_ROLE", "")).strip().lower()
        cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
        if not worker_enabled:
            return False
        return (not collection_enabled) or deployment_role == "cloud" or not cloud_database_url

    @staticmethod
    def _current_checkpoint_scope() -> str:
        return get_current_checkpoint_scope_from_env(dry_run=False)

    @staticmethod
    def _task_matches_scope(task: CloudBClassSyncTask, checkpoint_scope: str) -> bool:
        metadata = task.metadata_json or {}
        task_scope = metadata.get("checkpoint_scope")
        if task_scope is None:
            return True
        return task_scope in {checkpoint_scope, "b_class"}

    async def get_runtime_summary(self, runtime_health: dict | None = None) -> dict:
        now = datetime.now(timezone.utc)
        current_scope = self._current_checkpoint_scope()
        running_tasks = (
            await self.db.execute(
                select(CloudBClassSyncTask).where(CloudBClassSyncTask.status == "running")
            )
        ).scalars().all()
        legacy_scope_stale_count = sum(
            1
            for task in running_tasks
            if not self._task_matches_scope(task, current_scope)
            and task.lease_expires_at is not None
            and _as_utc(task.lease_expires_at) is not None
            and _as_utc(task.lease_expires_at) < now
        )
        running_tasks = [task for task in running_tasks if self._task_matches_scope(task, current_scope)]
        active_tasks = [
            task
            for task in running_tasks
            if (
                task.lease_expires_at is None
                or _as_utc(task.lease_expires_at) is None
                or _as_utc(task.lease_expires_at) >= now
            )
        ]
        stale_tasks = [
            task
            for task in running_tasks
            if task.lease_expires_at is not None
            and _as_utc(task.lease_expires_at) is not None
            and _as_utc(task.lease_expires_at) < now
        ]
        active_count = len(active_tasks)
        running_task = active_tasks[0] if active_tasks else None
        runtime_error = (runtime_health or {}).get("last_error")
        stale_error = "stale_running_recovered_on_startup" if stale_tasks else None
        error_code, error_summary, error_action_hint = _classify_cloud_sync_error(runtime_error or stale_error)
        task_started_at = _as_utc(getattr(running_task, "last_attempt_started_at", None))
        task_heartbeat_at = _as_utc(getattr(running_task, "heartbeat_at", None))
        task_lease_expires_at = _as_utc(getattr(running_task, "lease_expires_at", None))
        current_task_run_seconds = (
            int((now - task_started_at).total_seconds()) if task_started_at is not None else None
        )
        seconds_since_task_heartbeat = (
            int((now - task_heartbeat_at).total_seconds()) if task_heartbeat_at is not None else None
        )
        task_lease_expired = (
            task_lease_expires_at is not None and task_lease_expires_at < now
        )
        worker_status = (runtime_health or {}).get("status", "not_started")
        if worker_status == "running":
            if stale_tasks or task_lease_expired:
                worker_status = "degraded"
            elif runtime_error:
                worker_status = "error"
        payload = CloudSyncRuntimeSummary(
            worker_status=worker_status,
            worker_id=(runtime_health or {}).get("worker_id"),
            is_running=active_count > 0,
            active_task_count=active_count,
            stale_running_count=len(stale_tasks),
            current_job_id=getattr(running_task, "job_id", None),
            current_source_table_name=getattr(running_task, "source_table_name", None),
            last_heartbeat_at=(runtime_health or {}).get("last_heartbeat_at"),
            last_runtime_heartbeat_at=(runtime_health or {}).get("last_runtime_heartbeat_at"),
            task_heartbeat_at=_iso(task_heartbeat_at),
            task_lease_expires_at=_iso(task_lease_expires_at),
            task_started_at=_iso(task_started_at),
            current_task_run_seconds=current_task_run_seconds,
            seconds_since_task_heartbeat=seconds_since_task_heartbeat,
            task_lease_expired=task_lease_expired,
            recent_recovery_at=(runtime_health or {}).get("last_recovered_at"),
            recent_recovery_count=int((runtime_health or {}).get("last_recovered_count") or 0),
            last_error=_sanitize_error_text((runtime_health or {}).get("last_error")),
            error_code=error_code,
            error_summary=error_summary,
            error_action_hint=error_action_hint,
            current_checkpoint_scope=current_scope,
            legacy_scope_stale_count=legacy_scope_stale_count,
        )
        return payload.model_dump()

    async def list_history(self, *, limit: int = 20) -> list[dict]:
        tasks = (
            await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit))
        ).scalars().all()
        return [
            CloudSyncHistoryRow(
                job_id=task.job_id,
                source_table_name=task.source_table_name,
                trigger_source=task.trigger_source,
                result_status=task.status,
                started_at=_iso(task.last_attempt_started_at),
                finished_at=_iso(task.last_attempt_finished_at or task.finished_at),
                last_error=_sanitize_error_text(task.last_error),
            ).model_dump()
            for task in tasks
        ]

    async def get_settings(self) -> dict:
        return CloudSyncSettings(
            auto_sync_enabled=await self._auto_sync_enabled(),
            pause_mode="buffer_backlog",
        ).model_dump()

    def _serialize_task(self, task: CloudBClassSyncTask, *, file_context=None, table_context=None) -> CloudSyncTaskRow:
        return CloudSyncTaskRow(
            job_id=task.job_id,
            status=task.status,
            source_table_name=task.source_table_name,
            attempt_count=int(task.attempt_count or 0),
            trigger_source=task.trigger_source,
            source_file_id=task.source_file_id,
            claimed_by=task.claimed_by,
            next_retry_at=_iso(task.next_retry_at),
            lease_expires_at=_iso(task.lease_expires_at),
            heartbeat_at=_iso(task.heartbeat_at),
            last_attempt_started_at=_iso(task.last_attempt_started_at),
            last_attempt_finished_at=_iso(task.last_attempt_finished_at),
            projection_status=task.projection_status,
            projection_preset=task.projection_preset,
            last_error=_sanitize_error_text(task.last_error),
            error_code=task.error_code,
            created_at=_iso(task.created_at),
            updated_at=_iso(task.updated_at),
            finished_at=_iso(task.finished_at),
            metadata=task.metadata_json or {},
            lifecycle=self._build_lifecycle_state(task, file_context, table_context),
            receive_log=self._build_receive_log_state((table_context or {}).get("receive")),
        )

    def _serialize_task_state(self, task: CloudBClassSyncTask | None) -> CloudSyncLatestTaskState:
        if task is None:
            return CloudSyncLatestTaskState()
        return CloudSyncLatestTaskState(**self._serialize_task(task).model_dump())

    def _probe_cloud_db_health(self) -> dict:
        cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
        if not cloud_database_url:
            return {
                "status": "unknown",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": None,
            }

        try:
            parsed = make_url(cloud_database_url)
            host = parsed.host or "127.0.0.1"
            port = int(parsed.port or 5432)
        except Exception as exc:
            return {
                "status": "unreachable",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": _sanitize_error_text(str(exc)),
            }

        ok, error = _probe_tcp_target(host, port)
        return {
            "status": "reachable" if ok else "unreachable",
            "last_checked_at": _iso(datetime.now(timezone.utc)),
            "error": error,
        }

    def _probe_tunnel_health(self, cloud_db_health: dict) -> dict:
        tunnel_enabled = str(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED", "")).lower() in {"1", "true", "yes", "on"}
        tunnel_host = os.getenv("CLOUD_SYNC_TUNNEL_HOST")
        tunnel_port = os.getenv("CLOUD_SYNC_TUNNEL_PORT")
        cloud_database_url = os.getenv("CLOUD_DATABASE_URL")

        if tunnel_enabled and tunnel_host and tunnel_port:
            ok, error = _probe_tcp_target(tunnel_host, int(tunnel_port))
            return {
                "status": "healthy" if ok else "unhealthy",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": error,
            }

        if cloud_database_url:
            try:
                parsed = make_url(cloud_database_url)
                if (parsed.host or "").lower() in {"127.0.0.1", "localhost"}:
                    return {
                        "status": "healthy" if cloud_db_health["status"] == "reachable" else "unhealthy",
                        "last_checked_at": _iso(datetime.now(timezone.utc)),
                        "error": cloud_db_health.get("error"),
                    }
            except Exception:
                pass

        return {
            "status": "unknown",
            "last_checked_at": _iso(datetime.now(timezone.utc)),
            "error": None,
        }

    async def _load_catalog_backlog_summary(self) -> tuple[int, int, int]:
        try:
            rows = (
                await self.db.execute(select(CatalogFile.status, CatalogFile.first_seen_at))
            ).all()
        except Exception:
            return 0, 0, 0

        now = datetime.now(timezone.utc)
        pending = 0
        overdue = 0
        processing = 0
        for status, first_seen_at in rows:
            normalized_status = str(status or "").strip().lower()
            if normalized_status == "pending":
                pending += 1
                seen_at = _as_utc(first_seen_at)
                if seen_at is not None and (now - seen_at).total_seconds() > 600:
                    overdue += 1
            elif normalized_status == "processing":
                processing += 1
        return pending, overdue, processing

    async def _load_refresh_queue_counts(self) -> dict[str, int]:
        try:
            rows = (
                await self.db.execute(
                    select(RefreshQueueTask.status).where(RefreshQueueTask.trigger_type == "cloud_sync")
                )
            ).all()
        except Exception:
            return {"pending": 0, "running": 0, "failed": 0}

        counts = {"pending": 0, "running": 0, "failed": 0}
        for (status,) in rows:
            normalized = str(status or "").strip().lower()
            if normalized in counts:
                counts[normalized] += 1
        return counts

    async def _load_latest_receive_by_table(self) -> dict[str, CloudSyncReceiveLog]:
        try:
            rows = (
                await self.db.execute(
                    select(CloudSyncReceiveLog).order_by(CloudSyncReceiveLog.id.desc())
                )
            ).scalars().all()
        except Exception:
            return {}

        latest: dict[str, CloudSyncReceiveLog] = {}
        for row in rows:
            latest.setdefault(row.source_table_name, row)
        return latest

    async def _load_latest_refresh_by_table(self) -> dict[str, RefreshQueueTask]:
        try:
            rows = (
                await self.db.execute(
                    select(RefreshQueueTask).where(RefreshQueueTask.trigger_type == "cloud_sync").order_by(RefreshQueueTask.id.desc())
                )
            ).scalars().all()
        except Exception:
            return {}

        latest: dict[str, RefreshQueueTask] = {}
        for row in rows:
            context = row.context_json or {}
            source_table_name = context.get("source_table_name")
            if not source_table_name:
                continue
            latest.setdefault(source_table_name, row)
        return latest

    async def _load_file_context(self, file_ids: list[int]) -> dict[int, dict]:
        normalized_ids = sorted({int(file_id) for file_id in file_ids if file_id is not None})
        if not normalized_ids:
            return {}
        context: dict[int, dict] = {file_id: {"catalog": None, "ingest_task": None} for file_id in normalized_ids}
        try:
            file_rows = (
                await self.db.execute(select(CatalogFile).where(CatalogFile.id.in_(normalized_ids)))
            ).scalars().all()
            for row in file_rows:
                context[row.id]["catalog"] = row
        except Exception:
            pass
        try:
            ingest_tasks = (
                await self.db.execute(
                    select(TaskCenterTask)
                    .where(TaskCenterTask.task_type == "single_file", TaskCenterTask.source_file_id.in_(normalized_ids))
                    .order_by(TaskCenterTask.id.desc())
                )
            ).scalars().all()
            for row in ingest_tasks:
                context.setdefault(row.source_file_id, {"catalog": None, "ingest_task": None})
                current = context[row.source_file_id].get("ingest_task")
                if current is None:
                    context[row.source_file_id]["ingest_task"] = row
        except Exception:
            pass
        return context

    async def _load_table_context(self, table_names: list[str]) -> dict[str, dict]:
        normalized_names = sorted({str(name).strip() for name in table_names if str(name).strip()})
        receive_by_table = await self._load_latest_receive_by_table()
        refresh_by_table = await self._load_latest_refresh_by_table()
        return {
            table_name: {
                "receive": receive_by_table.get(table_name),
                "refresh": refresh_by_table.get(table_name),
            }
            for table_name in normalized_names
        }

    @staticmethod
    def _map_catalog_status_to_ingest(status: str | None) -> str | None:
        normalized = str(status or "").strip().lower()
        if not normalized:
            return None
        mapping = {
            "pending": "pending",
            "processing": "running",
            "validated": "running",
            "ingested": "completed",
            "quarantined": "completed",
            "failed": "failed",
            "template_update_required": "template_update_required",
            "partial_success": "partial_success",
        }
        return mapping.get(normalized, normalized)

    @staticmethod
    def _build_receive_log_state(receive_row: CloudSyncReceiveLog | None) -> CloudSyncReceiveLogState:
        if receive_row is None:
            return CloudSyncReceiveLogState()
        return CloudSyncReceiveLogState(
            last_receive_at=_iso(getattr(receive_row, "created_at", None)),
            last_written_rows=getattr(receive_row, "written_rows", None),
            latest_business_date=str(getattr(receive_row, "business_date_max", None) or "") or None,
            status=getattr(receive_row, "status", None),
        )

    def _build_lifecycle_state(self, task: CloudBClassSyncTask | None, file_context: dict | None, table_context: dict | None) -> CloudSyncLifecycleState:
        catalog = (file_context or {}).get("catalog")
        ingest_task = (file_context or {}).get("ingest_task")
        refresh_task = (table_context or {}).get("refresh")
        collection_task_id = None
        collection_status = None
        local_ingest_status = None
        if catalog is not None:
            collection_status = "completed"
            metadata = catalog.file_metadata if isinstance(catalog.file_metadata, dict) else {}
            collection_task_id = metadata.get("collection_task_id") or metadata.get("task_id")
            local_ingest_status = self._map_catalog_status_to_ingest(getattr(catalog, "status", None))
        if ingest_task is not None:
            local_ingest_status = getattr(ingest_task, "status", None) or local_ingest_status
        cloud_refresh_status = getattr(refresh_task, "status", None)
        if cloud_refresh_status is None and task is not None:
            cloud_refresh_status = getattr(task, "projection_status", None)
        return CloudSyncLifecycleState(
            collection_status=collection_status,
            local_ingest_status=local_ingest_status,
            cloud_sync_status=getattr(task, "status", None) if task is not None else None,
            cloud_refresh_status=cloud_refresh_status,
            source_file_id=getattr(task, "source_file_id", None) if task is not None else getattr(catalog, "id", None),
            collection_task_id=collection_task_id,
            ingest_task_id=getattr(ingest_task, "task_id", None),
        )
