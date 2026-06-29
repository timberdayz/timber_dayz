from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, text

from modules.core.db import CatalogFile, CloudBClassSyncTask


CLOUD_SYNC_RECOVERABLE_ERROR_CODES = {
    "legacy_scope_stale_recovered",
    "cloud_receive_log_missing",
    "cloud_receive_log_table_missing_after_migration",
    "cloud_db_transient_unavailable",
    "worker_lost",
    "lease_expired",
    "task_stale_running",
}

CATALOG_FILE_TRANSIENT_ERROR_CODES = {
    "process_pool_broken",
    "worker_lost",
    "temporary_io_error",
    "cloud_db_transient_unavailable",
}


class CloudSyncAutoRecoveryService:
    """Recover known-safe local ingest and cloud sync stalls."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _metadata_with_recovery(
        metadata: dict[str, Any] | None,
        *,
        previous_status: str,
        previous_error_code: str | None,
        recovery_reason: str,
        attempt_override: bool = False,
    ) -> dict[str, Any]:
        next_metadata = dict(metadata or {})
        next_metadata["auto_recovery"] = {
            "recovered_by": "auto_recovery",
            "recovery_reason": recovery_reason,
            "previous_status": previous_status,
            "previous_error_code": previous_error_code,
            "recovered_at": CloudSyncAutoRecoveryService._utcnow().isoformat(),
            "attempt_override": attempt_override,
        }
        return next_metadata

    def recover_cloud_sync_tasks(self, *, limit: int = 20) -> dict[str, Any]:
        now = self._utcnow()
        result = self.db.execute(
            select(CloudBClassSyncTask)
            .where(
                or_(
                    CloudBClassSyncTask.status == "failed",
                    CloudBClassSyncTask.status == "running",
                )
            )
            .order_by(CloudBClassSyncTask.updated_at.asc().nullsfirst())
            .limit(limit)
        )
        candidates = list(result.scalars().all())
        recovered: list[str] = []

        for task in candidates:
            previous_status = getattr(task, "status", None)
            previous_error_code = getattr(task, "error_code", None)
            recovery_reason = previous_error_code
            attempt_override = False

            if previous_status == "running":
                lease_expires_at = getattr(task, "lease_expires_at", None)
                if lease_expires_at is None or lease_expires_at > now:
                    continue
                recovery_reason = "task_stale_running"
            elif previous_status == "failed":
                if previous_error_code not in CLOUD_SYNC_RECOVERABLE_ERROR_CODES:
                    continue
                attempt_override = int(getattr(task, "attempt_count", 0) or 0) >= 20
            else:
                continue

            task.status = "pending"
            task.next_retry_at = now
            task.claimed_by = None
            task.lease_expires_at = None
            task.heartbeat_at = None
            task.last_error = None
            task.error_code = None
            task.finished_at = None
            task.updated_at = now
            task.metadata_json = self._metadata_with_recovery(
                getattr(task, "metadata_json", None),
                previous_status=previous_status,
                previous_error_code=previous_error_code,
                recovery_reason=recovery_reason or "recoverable_cloud_sync_failure",
                attempt_override=attempt_override,
            )
            recovered.append(getattr(task, "job_id", str(getattr(task, "id", ""))))

        if recovered:
            self.db.commit()

        return {
            "status": "success",
            "recovered": len(recovered),
            "job_ids": recovered,
        }

    def recover_failed_catalog_files(self, *, limit: int = 20) -> dict[str, Any]:
        result = self.db.execute(
            select(CatalogFile)
            .where(CatalogFile.status == "failed")
            .order_by(CatalogFile.first_seen_at.asc().nullsfirst())
            .limit(limit)
        )
        files = list(result.scalars().all())
        recovered: list[int] = []
        now = self._utcnow()

        for file_record in files:
            metadata = dict(getattr(file_record, "file_metadata", None) or {})
            auto_meta = dict(metadata.get("auto_ingest") or {})
            error_code = auto_meta.get("error_code") or auto_meta.get("last_error_code")
            if error_code not in CATALOG_FILE_TRANSIENT_ERROR_CODES:
                continue
            previous_status = getattr(file_record, "status", None)
            file_record.status = "pending"
            file_record.error_message = None
            auto_meta.update(
                {
                    "last_status": "auto_requeued",
                    "last_reason": error_code,
                    "current_task_id": None,
                    "recovered_at": now.isoformat(),
                    "recovered_by": "auto_recovery",
                    "previous_status": previous_status,
                }
            )
            metadata["auto_ingest"] = auto_meta
            file_record.file_metadata = metadata
            recovered.append(int(file_record.id))

        if recovered:
            self.db.commit()

        return {
            "status": "success",
            "recovered": len(recovered),
            "file_ids": recovered,
        }

    def enqueue_overdue_pending_catalog_files(
        self,
        *,
        limit: int = 20,
        overdue_minutes: int = 10,
    ) -> dict[str, Any]:
        from backend.tasks.data_sync_tasks import sync_single_file_task

        now = self._utcnow()
        cutoff = now - timedelta(minutes=overdue_minutes)
        result = self.db.execute(
            select(CatalogFile)
            .where(CatalogFile.status == "pending")
            .where(CatalogFile.first_seen_at <= cutoff)
            .order_by(CatalogFile.first_seen_at.asc().nullsfirst())
            .limit(limit)
        )
        files = list(result.scalars().all())
        enqueued: list[int] = []

        for file_record in files:
            if getattr(file_record, "status", None) != "pending":
                continue
            first_seen_at = getattr(file_record, "first_seen_at", None)
            if first_seen_at is None:
                continue
            if first_seen_at.tzinfo is None:
                first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
            if first_seen_at > cutoff:
                continue

            task_result = sync_single_file_task.apply_async(
                kwargs={"file_id": int(file_record.id)},
                queue="data_sync",
            )
            metadata = dict(getattr(file_record, "file_metadata", None) or {})
            auto_meta = dict(metadata.get("auto_ingest") or {})
            auto_meta.update(
                {
                    "last_status": "auto_enqueued",
                    "last_reason": "pending_catalog_file_overdue",
                    "current_task_id": getattr(task_result, "id", None),
                    "recovered_at": now.isoformat(),
                    "recovered_by": "auto_recovery",
                    "previous_status": "pending",
                }
            )
            metadata["auto_ingest"] = auto_meta
            file_record.file_metadata = metadata
            enqueued.append(int(file_record.id))

        if enqueued:
            self.db.commit()

        return {
            "status": "success",
            "enqueued": len(enqueued),
            "file_ids": enqueued,
        }

    def release_orphan_auto_ingest_locks(
        self,
        *,
        lock_key: int = 928451203,
        idle_seconds: int = 300,
        terminate: bool = True,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            text(
                """
                SELECT
                    a.pid,
                    EXTRACT(EPOCH FROM (now() - COALESCE(a.state_change, a.query_start)))::int
                        AS lock_age_seconds,
                    (
                        SELECT COUNT(*)
                        FROM task_center_tasks t
                        WHERE t.task_type = 'auto_ingest'
                          AND t.status = 'running'
                    ) AS running_auto_ingest_tasks
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE l.locktype = 'advisory'
                  AND l.granted = true
                  AND l.objid = :lock_key
                  AND a.state = 'idle'
                  AND EXTRACT(EPOCH FROM (now() - COALESCE(a.state_change, a.query_start))) >= :idle_seconds
                """
            ),
            {"lock_key": lock_key, "idle_seconds": idle_seconds},
        ).mappings().all()
        orphaned = [
            dict(row)
            for row in rows
            if int(row.get("running_auto_ingest_tasks") or 0) == 0
        ]
        terminated: list[int] = []
        if terminate:
            for row in orphaned:
                pid = int(row["pid"])
                self.db.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
                terminated.append(pid)
            if terminated:
                self.db.commit()
        return {
            "status": "success",
            "orphaned": len(orphaned),
            "terminated": terminated,
        }

    def run_once(self, *, limit: int = 20) -> dict[str, Any]:
        cloud = self.recover_cloud_sync_tasks(limit=limit)
        files = self.recover_failed_catalog_files(limit=limit)
        pending_files = self.enqueue_overdue_pending_catalog_files(limit=limit)
        return {
            "status": "success",
            "cloud_sync": cloud,
            "catalog_files": files,
            "pending_catalog_files": pending_files,
        }
