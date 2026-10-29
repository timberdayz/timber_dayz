from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select, text

from backend.services.data_sync_file_state_service import (
    apply_template_blocked_state,
    resolve_template_blocked_catalog_status,
)
from backend.services.spreadsheet_header_reader import get_spreadsheet_header_reader
from backend.services.template_contract_service import read_template_contract
from modules.core.db import (
    CatalogFile,
    CloudBClassSyncTask,
    FieldMappingTemplateFamily,
)


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

    def _domain_has_template_family(self, file_record) -> bool:
        """该文件所属数据域下是否还存在**任何**模板族。

        [*] 保守判定(宁可放过, 不误伤):
        跨 family 变体接管的边界是「同平台同数据域」
        (见 ``backend/services/template_variant_takeover_service.py``),
        所以只要同域下还有任何一个模板族, 就**不能**断定这个文件没有模板 ——
        它可能被同域其它粒度的变体接管。
        只有「同平台同数据域下一个族都没有」才是确定无模板。
        """
        platform = getattr(file_record, "platform_code", None) or getattr(
            file_record, "source_platform", None
        )
        domain = getattr(file_record, "data_domain", None)
        if not platform or not domain:
            # 维度不全 -> 不下结论, 保守放行
            return True
        try:
            count = self.db.execute(
                select(func.count(FieldMappingTemplateFamily.id)).where(
                    FieldMappingTemplateFamily.platform == platform,
                    FieldMappingTemplateFamily.data_domain == domain,
                )
            ).scalar()
        except Exception:  # noqa: BLE001
            # 查不到就不下结论(宁可放过, 也不误伤有模板的文件)
            return True
        return bool(count)

    def _source_file_exists(self, file_record) -> bool:
        """源文件是否还在磁盘上。"""
        raw_path = getattr(file_record, "file_path", None)
        if not raw_path:
            return False
        try:
            resolved = get_spreadsheet_header_reader(
                log_prefix="AutoRecovery"
            ).resolve_safe_path(raw_path)
        except Exception:  # noqa: BLE001
            return False
        try:
            return Path(resolved).exists()
        except Exception:  # noqa: BLE001
            return False

    def _precheck_ingest_feasible(self, file_record) -> tuple[bool, str | None]:
        """兜底入队前的可行性预检。

        返回 ``(是否值得入队, 不入队时的原因)``。

        [*] 兜底通道的职责是「捞起被漏掉的文件」, 不是「把确定性失败的活
            再塞回队列」。一个文件如果**确定**没有可用模板, 重试多少次都
            不会成功 —— 让它进队列只会制造无限重试闭环
            (实测: 8 个文件 2 天内 72 次完全无效的同步任务)。
        """
        # 1) 契约模板: 文件自带「采集当时生效的那一版模板」,
        #    即使当前没有模板族也能解释这个文件
        if read_template_contract(file_record):
            return True, None
        # 2) 同域还有模板族 -> 可能有同粒度族, 也可能被同域其它族接管
        if self._domain_has_template_family(file_record):
            return True, None
        # 3) 确定无模板
        reason = (
            f"无模板(platform={getattr(file_record, 'platform_code', None)}, "
            f"domain={getattr(file_record, 'data_domain', None)}, "
            f"granularity={getattr(file_record, 'granularity', None)}, "
            f"sub_domain={getattr(file_record, 'sub_domain', None)}), 需人工创建模板"
        )
        return False, reason

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
        blocked: list[int] = []

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

            file_id = int(file_record.id)

            # [*] 可行性预检: 确定无模板的文件**不入队**, 直接落终态。
            #     否则它会被兜底反复捞起 -> 看门狗判超时 -> 回退 pending -> 无限循环。
            feasible, blocked_reason = self._precheck_ingest_feasible(file_record)
            if not feasible:
                target_status = resolve_template_blocked_catalog_status(
                    source_exists=self._source_file_exists(file_record)
                )
                apply_template_blocked_state(
                    file_record,
                    target_status=target_status,
                    reason=blocked_reason or "无模板, 需人工创建模板",
                    status_info={
                        "template_status": "missing",
                        "governance_status": "missing_family",
                    },
                )
                blocked.append(file_id)
                continue

            # [*] 修复: sync_single_file_task 的 task_id 是必填参数,
            # 缺失会在 Celery 提交阶段抛 TypeError, 让整个兜底任务每分钟失败。
            progress_task_id = f"single_file_{file_id}_{uuid4().hex[:8]}"
            task_result = sync_single_file_task.apply_async(
                kwargs={
                    "file_id": file_id,
                    "task_id": progress_task_id,
                },
                queue="data_sync",
            )
            metadata = dict(getattr(file_record, "file_metadata", None) or {})
            auto_meta = dict(metadata.get("auto_ingest") or {})
            auto_meta.update(
                {
                    "last_status": "auto_enqueued",
                    "last_reason": "pending_catalog_file_overdue",
                    # [*] current_task_id 必须与提交给 Celery 的 task_id 一致,
                    # 否则 sync_single_file 会把「自己认领的文件」误判为并发冲突而跳过。
                    "current_task_id": progress_task_id,
                    "celery_task_id": getattr(task_result, "id", None),
                    # [*] 认领: 立刻置 processing, 避免下一分钟的兜底任务重复入队。
                    # 若 Celery 任务最终没跑起来, 看门狗会依据 processing_started_at 把它回退为 pending。
                    "processing_started_at": now.isoformat(),
                    "claimed_by": "auto_recovery",
                    "recovered_at": now.isoformat(),
                    "recovered_by": "auto_recovery",
                    "previous_status": "pending",
                }
            )
            metadata["auto_ingest"] = auto_meta
            file_record.file_metadata = metadata
            file_record.status = "processing"
            enqueued.append(file_id)

        if enqueued or blocked:
            self.db.commit()

        return {
            "status": "success",
            "enqueued": len(enqueued),
            "file_ids": enqueued,
            "blocked": len(blocked),
            "blocked_file_ids": blocked,
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
