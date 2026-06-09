"""
定时任务 - Celery Beat定时执行的任务
包含:物化视图刷新、库存告警、应收账款检查、数据库备份
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

# 添加项目根目录到Python路径
from modules.core.path_manager import get_project_root
root_dir = get_project_root()
sys.path.insert(0, str(root_dir))

from backend.celery_app import celery_app
from backend.models.database import SessionLocal, reset_async_engine_pool_for_new_loop
from modules.core.db import CatalogFile
from sqlalchemy import select, text
import logging

logger = logging.getLogger(__name__)

AUTO_INGEST_MAX_FILES_PER_RUN = max(
    1, int(os.getenv("AUTO_INGEST_MAX_FILES_PER_RUN", "20"))
)
AUTO_INGEST_MAX_CONCURRENT = max(1, int(os.getenv("AUTO_INGEST_MAX_CONCURRENT", "1")))
AUTO_INGEST_STALE_TIMEOUT_MINUTES = max(
    1, int(os.getenv("AUTO_INGEST_STALE_TIMEOUT_MINUTES", "45"))
)
AUTO_INGEST_HEARTBEAT_INTERVAL_SECONDS = max(
    5, int(os.getenv("AUTO_INGEST_HEARTBEAT_INTERVAL_SECONDS", "30"))
)
AUTO_INGEST_STALE_WARNING_MINUTES = max(
    1, int(os.getenv("AUTO_INGEST_STALE_WARNING_MINUTES", "15"))
)
AUTO_INGEST_WATCHDOG_INTERVAL_MINUTES = max(
    1, int(os.getenv("AUTO_INGEST_WATCHDOG_INTERVAL_MINUTES", "5"))
)
AUTO_INGEST_LOCK_KEY = int(os.getenv("AUTO_INGEST_LOCK_KEY", "928451203"))
AUTO_INGEST_WATCHDOG_LOCK_KEY = int(os.getenv("AUTO_INGEST_WATCHDOG_LOCK_KEY", "928451204"))
AUTO_INGEST_SOURCE = "scheduled_tasks.auto_ingest_pending_files"


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def _get_session_dialect_name(db) -> str:
    bind = getattr(db, "bind", None)
    if bind is None and hasattr(db, "get_bind"):
        try:
            bind = db.get_bind()
        except Exception:
            bind = None
    return str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()


def _acquire_auto_ingest_lock(db, lock_key: int = AUTO_INGEST_LOCK_KEY) -> bool:
    if _get_session_dialect_name(db) != "postgresql":
        return True
    result = db.execute(
        text("SELECT pg_try_advisory_lock(:lock_key)"),
        {"lock_key": lock_key},
    )
    return bool(result.scalar())


def _release_auto_ingest_lock(db, lock_key: int = AUTO_INGEST_LOCK_KEY) -> None:
    if _get_session_dialect_name(db) != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_unlock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _parse_auto_ingest_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _append_auto_ingest_error(details: Dict[str, Any] | None, message: str) -> Dict[str, Any]:
    next_details = dict(details or {})
    errors = list(next_details.get("errors") or [])
    errors.append({"message": message})
    next_details["errors"] = errors
    next_details.setdefault("warnings", [])
    next_details["message"] = message
    next_details.setdefault("task_details", {})
    return next_details


def _auto_ingest_task_activity_at(task) -> datetime | None:
    for attr in ("heartbeat_at", "updated_at", "started_at"):
        parsed = _parse_auto_ingest_timestamp(getattr(task, attr, None))
        if parsed is not None:
            return parsed
    return None


def _recover_stale_auto_ingest_records(
    db,
    timeout_minutes: int = AUTO_INGEST_STALE_TIMEOUT_MINUTES,
) -> Dict[str, int]:
    from modules.core.db import TaskCenterTask

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=timeout_minutes)
    timeout_message = f"auto ingest timed out after {timeout_minutes} minutes"
    recovered_tasks = 0
    recovered_files = 0
    stale_task_ids: set[str] = set()

    try:
        stale_tasks = (
            db.execute(
                select(TaskCenterTask).where(
                    TaskCenterTask.task_type == "auto_ingest",
                    TaskCenterTask.status == "running",
                    TaskCenterTask.started_at < cutoff,
                )
            )
            .scalars()
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AutoIngest] stale task recovery skipped: %s", exc)
        stale_tasks = []

    for task in stale_tasks:
        if not all(hasattr(task, attr) for attr in ("status", "details_json")):
            continue
        activity_at = _auto_ingest_task_activity_at(task)
        if activity_at is None or activity_at >= cutoff:
            continue
        task.status = "failed"
        task.finished_at = now
        if hasattr(task, "heartbeat_at"):
            task.heartbeat_at = now
        task.error_summary = timeout_message
        next_details = _append_auto_ingest_error(task.details_json, timeout_message)
        task_details = dict(next_details.get("task_details") or {})
        task_details["recovered_by"] = "watchdog"
        task_details["recovered_at"] = now.isoformat()
        next_details["task_details"] = task_details
        task.details_json = next_details
        recovered_tasks += 1
        stale_task_ids.add(str(getattr(task, "task_id", "") or ""))

    try:
        processing_files = (
            db.execute(select(CatalogFile).where(CatalogFile.status == "processing"))
            .scalars()
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AutoIngest] stale file recovery skipped: %s", exc)
        processing_files = []

    for file_record in processing_files:
        if not all(hasattr(file_record, attr) for attr in ("file_metadata", "status")):
            continue
        meta = dict(file_record.file_metadata or {})
        auto_meta = dict(meta.get("auto_ingest") or {})
        started_at = _parse_auto_ingest_timestamp(auto_meta.get("processing_started_at"))
        claimed_task_id = str(auto_meta.get("current_task_id") or "").strip()
        should_recover = bool(claimed_task_id and claimed_task_id in stale_task_ids)
        if not should_recover and (started_at is None or started_at >= cutoff):
            continue
        auto_meta["last_status"] = "stale_recovered"
        auto_meta["last_recovered_at"] = now.isoformat()
        auto_meta["current_task_id"] = None
        meta["auto_ingest"] = auto_meta
        file_record.file_metadata = meta
        file_record.status = "pending"
        file_record.error_message = "自动入库任务超时，已回退等待重试"
        recovered_files += 1

    if recovered_tasks or recovered_files:
        db.commit()

    return {"tasks": recovered_tasks, "files": recovered_files}


def _create_auto_ingest_task_record(
    db,
    pending_ids: List[int],
    max_files: int,
    max_concurrent: int,
) -> str | None:
    if not pending_ids:
        return None

    try:
        from backend.services.task_center_sync_service import TaskCenterSyncService

        started_at = datetime.now(timezone.utc)
        task_id = f"auto_ingest_{started_at.strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        task_center = TaskCenterSyncService(db)
        task_center.create_task(
            task_id=task_id,
            task_family="data_sync",
            task_type="auto_ingest",
            status="running",
            trigger_source="auto_ingest",
            total_items=len(pending_ids),
            processed_items=0,
            success_items=0,
            failed_items=0,
            skipped_items=0,
            total_rows=0,
            processed_rows=0,
            valid_rows=0,
            error_rows=0,
            quarantined_rows=0,
            progress_percent=0.0,
            started_at=started_at,
            heartbeat_at=started_at,
            details_json={
                "errors": [],
                "warnings": [],
                "message": "auto ingest running",
                "row_progress": 0.0,
                "task_details": {
                    "source": AUTO_INGEST_SOURCE,
                    "max_files": max_files,
                    "max_concurrent": max_concurrent,
                    "file_ids": list(pending_ids),
                    "success_files": 0,
                    "failed_files": 0,
                    "skipped_files": 0,
                    "quarantined_files": 0,
                    "skipped_template_update": 0,
                    "skipped_no_template": 0,
                    "files": [],
                },
            },
        )
        for file_id in pending_ids:
            try:
                task_center.add_link(
                    task_id,
                    subject_type="catalog_file",
                    subject_id=str(file_id),
                )
            except Exception as link_exc:  # noqa: BLE001
                logger.warning(
                    "[AutoIngest] failed to link task-center record %s to file %s: %s",
                    task_id,
                    file_id,
                    link_exc,
                    exc_info=True,
                )
        return task_id
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[AutoIngest] failed to create task-center record: %s",
            exc,
            exc_info=True,
        )
        return None


def _auto_ingest_result_status(item: Dict[str, Any]) -> str:
    status = str(item.get("status") or "").strip()
    try:
        quarantined = int(item.get("quarantined") or 0)
    except (TypeError, ValueError):
        quarantined = 0
    if quarantined > 0 and status in {"", "success"}:
        return "quarantined"
    if status:
        return status
    if item.get("success") is True:
        return "success"
    return "failed"


def _auto_ingest_result_message(item: Dict[str, Any]) -> str:
    return str(
        item.get("message")
        or item.get("error")
        or item.get("detail")
        or ""
    )


def _build_auto_ingest_task_details(
    summary: Dict[str, int],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    files = []
    errors = []
    warnings = []

    for item in results:
        safe_item = item if isinstance(item, dict) else {"status": "failed", "message": str(item)}
        status = _auto_ingest_result_status(safe_item)
        message = _auto_ingest_result_message(safe_item)
        file_entry = {
            "file_id": safe_item.get("file_id"),
            "file_name": safe_item.get("file_name"),
            "status": status,
            "error_code": safe_item.get("error_code"),
            "message": message,
        }
        files.append(file_entry)
        if status == "failed":
            errors.append(file_entry)
        elif status == "skipped":
            warnings.append(file_entry)

    message = (
        "Auto ingest completed: "
        f"success={summary.get('succeeded', 0)}, "
        f"quarantined={summary.get('quarantined', 0)}, "
        f"failed={summary.get('failed', 0)}, "
        f"skipped={summary.get('skipped', 0)}"
    )

    return {
        "errors": errors,
        "warnings": warnings,
        "message": message,
        "row_progress": 0.0,
        "task_details": {
            "success_files": summary.get("succeeded", 0),
            "failed_files": summary.get("failed", 0),
            "skipped_files": summary.get("skipped", 0),
            "quarantined_files": summary.get("quarantined", 0),
            "skipped_template_update": summary.get("skipped_template_update", 0),
            "skipped_no_template": summary.get("skipped_no_template", 0),
            "files": files,
        },
    }


def _summarize_auto_ingest_results(results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "processed": len(results),
        "succeeded": 0,
        "quarantined": 0,
        "failed": 0,
        "skipped": 0,
        "skipped_no_template": 0,
        "skipped_template_update": 0,
    }
    for item in results:
        safe_item = item if isinstance(item, dict) else {"status": "failed", "message": str(item)}
        status = _auto_ingest_result_status(safe_item)
        if status == "success":
            summary["succeeded"] += 1
        elif status == "quarantined":
            summary["quarantined"] += 1
        elif status == "failed":
            summary["failed"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
            message = safe_item.get("message", "")
            message_lower = str(message).lower()
            if (
                safe_item.get("error_code") == "NO_TEMPLATE"
                or safe_item.get("skip_reason") == "no_template"
                or "no_template" in message_lower
                or "no template" in message_lower
                or "无模板" in str(message)
            ):
                summary["skipped_no_template"] += 1
            if safe_item.get("error_code") == "TEMPLATE_UPDATE_REQUIRED":
                summary["skipped_template_update"] += 1
    return summary


def _update_auto_ingest_task_progress(
    db,
    task_id: str | None,
    total_files: int,
    partial_results: List[Dict[str, Any]],
    max_files: int,
    max_concurrent: int,
    current_item: str | None = None,
) -> None:
    if not task_id or total_files <= 0:
        return
    try:
        from backend.services.task_center_sync_service import TaskCenterSyncService

        task_center = TaskCenterSyncService(db)
        task = task_center.get_task(task_id)
        if task is None:
            return
        summary = _summarize_auto_ingest_results(partial_results)
        details = _build_auto_ingest_task_details(summary, partial_results[-20:])
        details["task_details"]["max_files"] = max_files
        details["task_details"]["max_concurrent"] = max_concurrent
        task_center.update_task(
            task,
            processed_items=summary["processed"],
            success_items=summary["succeeded"],
            failed_items=summary["failed"],
            skipped_items=summary["skipped"],
            progress_percent=round((summary["processed"] / total_files) * 100, 2),
            heartbeat_at=datetime.now(timezone.utc),
            current_item=current_item,
            details_json=details,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[AutoIngest] failed to update task progress %s: %s",
            task_id,
            exc,
            exc_info=True,
        )


def _resolve_auto_ingest_task_status(summary: Dict[str, int]) -> str:
    processed = int(summary.get("processed", 0) or 0)
    failed = int(summary.get("failed", 0) or 0)
    skipped = int(summary.get("skipped", 0) or 0)
    if processed > 0 and failed >= processed:
        return "failed"
    if failed > 0 or skipped > 0:
        return "partial_success"
    return "completed"


def _complete_auto_ingest_task_record(
    db,
    task_id: str | None,
    summary: Dict[str, int],
    results: List[Dict[str, Any]],
    max_files: int | None = None,
    max_concurrent: int | None = None,
) -> None:
    if not task_id:
        return

    try:
        from backend.services.task_center_sync_service import TaskCenterSyncService

        task_center = TaskCenterSyncService(db)
        task = task_center.get_task(task_id)
        if task is None:
            return
        details = _build_auto_ingest_task_details(summary, results)
        if max_files is not None:
            details["task_details"]["max_files"] = max_files
        if max_concurrent is not None:
            details["task_details"]["max_concurrent"] = max_concurrent
        task_center.update_task(
            task,
            status=_resolve_auto_ingest_task_status(summary),
            processed_items=summary.get("processed", 0),
            success_items=summary.get("succeeded", 0),
            failed_items=summary.get("failed", 0),
            skipped_items=summary.get("skipped", 0),
            progress_percent=100.0,
            heartbeat_at=datetime.now(timezone.utc),
            current_item=None,
            finished_at=datetime.now(timezone.utc),
            details_json=details,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[AutoIngest] failed to complete task-center record %s: %s",
            task_id,
            exc,
            exc_info=True,
        )


def _claim_auto_ingest_files(
    db,
    pending_ids: List[int],
    task_id: str | None,
) -> None:
    if not pending_ids:
        return
    now = datetime.now(timezone.utc)
    try:
        files = (
            db.execute(select(CatalogFile).where(CatalogFile.id.in_(pending_ids)))
            .scalars()
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AutoIngest] failed to load files for claim: %s", exc)
        return

    claimed_count = 0
    for file_record in files:
        if getattr(file_record, "status", None) != "pending":
            continue
        meta = dict(file_record.file_metadata or {})
        auto_meta = dict(meta.get("auto_ingest") or {})
        auto_meta["current_task_id"] = task_id
        auto_meta["processing_started_at"] = now.isoformat()
        auto_meta["claimed_by"] = AUTO_INGEST_SOURCE
        auto_meta["last_status"] = "claimed"
        meta["auto_ingest"] = auto_meta
        file_record.file_metadata = meta
        file_record.status = "processing"
        claimed_count += 1

    if claimed_count:
        db.commit()


def _fail_auto_ingest_task_record(db, task_id: str | None, error: Exception) -> None:
    if not task_id:
        return

    error_message = str(error)
    try:
        from backend.services.task_center_sync_service import TaskCenterSyncService

        task_center = TaskCenterSyncService(db)
        task = task_center.get_task(task_id)
        if task is None:
            return
        task_center.update_task(
            task,
            status="failed",
            heartbeat_at=datetime.now(timezone.utc),
            current_item=None,
            finished_at=datetime.now(timezone.utc),
            error_summary=error_message,
            details_json={
                "errors": [{"message": error_message}],
                "warnings": [],
                "message": error_message,
                "row_progress": 0.0,
                "task_details": {
                    "success_files": 0,
                    "failed_files": 0,
                    "skipped_files": 0,
                    "quarantined_files": 0,
                    "skipped_template_update": 0,
                    "skipped_no_template": 0,
                    "files": [],
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[AutoIngest] failed to mark task-center record %s as failed: %s",
            task_id,
            exc,
            exc_info=True,
        )


def _heartbeat_auto_ingest_task(
    db,
    task_id: str | None,
    *,
    current_item: str | None = None,
) -> None:
    if not task_id:
        return

    try:
        from backend.services.task_center_sync_service import TaskCenterSyncService

        task_center = TaskCenterSyncService(db)
        task = task_center.get_task(task_id)
        if task is None or getattr(task, "status", None) != "running":
            return
        updates: Dict[str, Any] = {"heartbeat_at": datetime.now(timezone.utc)}
        if current_item is not None:
            updates["current_item"] = current_item
        task_center.update_task(task, **updates)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[AutoIngest] failed to heartbeat task-center record %s: %s",
            task_id,
            exc,
            exc_info=True,
        )


@celery_app.task(name="backend.tasks.scheduled_tasks.cleanup_stale_auto_ingest_tasks")
def cleanup_stale_auto_ingest_tasks():
    db = SessionLocal()
    lock_acquired = False
    try:
        timeout_minutes = _int_env(
            "AUTO_INGEST_STALE_TIMEOUT_MINUTES",
            AUTO_INGEST_STALE_TIMEOUT_MINUTES,
        )
        lock_key = _int_env(
            "AUTO_INGEST_WATCHDOG_LOCK_KEY",
            AUTO_INGEST_WATCHDOG_LOCK_KEY,
            minimum=1,
        )
        lock_acquired = _acquire_auto_ingest_lock(db, lock_key)
        if not lock_acquired:
            logger.info("[AutoIngest] watchdog skipped because another cleanup is running")
            return {"status": "skipped", "reason": "auto_ingest_watchdog_already_running"}

        recovered = _recover_stale_auto_ingest_records(db, timeout_minutes=timeout_minutes)
        return {"status": "success", "recovered": recovered}
    except Exception as exc:  # noqa: BLE001
        logger.error("[AutoIngest] watchdog failed: %s", exc, exc_info=True)
        return {"status": "failed", "error": str(exc)}
    finally:
        if lock_acquired:
            try:
                _release_auto_ingest_lock(
                    db,
                    _int_env(
                        "AUTO_INGEST_WATCHDOG_LOCK_KEY",
                        AUTO_INGEST_WATCHDOG_LOCK_KEY,
                        minimum=1,
                    ),
                )
            except Exception as unlock_exc:  # noqa: BLE001
                logger.warning("[AutoIngest] failed to release watchdog advisory lock: %s", unlock_exc)
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.refresh_sales_materialized_views")
def refresh_sales_materialized_views():
    """
    刷新销售相关物化视图
    执行频率:每5分钟
    性能:增量刷新(CONCURRENTLY),不锁表
    """
    logger.warning(
        "[LegacyMV] refresh_sales_materialized_views is deprecated and skipped"
    )
    return {"status": "skipped", "reason": "legacy_materialized_view_task"}
    db = SessionLocal()
    
    try:
        logger.info("[REFRESH] Starting to refresh sales materialized views...")
        
        # 刷新日度销售视图
        logger.info("  Refreshing mv_daily_sales...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales"))
        db.commit()
        
        # 刷新周度销售视图(依赖日度视图)
        logger.info("  Refreshing mv_weekly_sales...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_weekly_sales"))
        db.commit()
        
        # 刷新月度销售视图
        logger.info("  Refreshing mv_monthly_sales...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_sales"))
        db.commit()
        
        # 刷新利润分析视图
        logger.info("  Refreshing mv_profit_analysis...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_profit_analysis"))
        db.commit()
        
        logger.info("[OK] Sales materialized views refreshed successfully")
        return {"status": "success", "refreshed_views": 4}
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to refresh sales views: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.refresh_inventory_finance_views")
def refresh_inventory_finance_views():
    """
    刷新库存和财务物化视图
    执行频率:每10分钟
    """
    logger.warning(
        "[LegacyMV] refresh_inventory_finance_views is deprecated and skipped"
    )
    return {"status": "skipped", "reason": "legacy_materialized_view_task"}
    db = SessionLocal()
    
    try:
        logger.info("[REFRESH] Starting to refresh inventory and finance views...")
        
        # 刷新库存汇总视图
        logger.info("  Refreshing mv_inventory_summary...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_inventory_summary"))
        db.commit()
        
        # 刷新财务总览视图
        logger.info("  Refreshing mv_financial_overview...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_financial_overview"))
        db.commit()
        
        logger.info("[OK] Inventory and finance views refreshed successfully")
        return {"status": "success", "refreshed_views": 2}
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to refresh inventory/finance views: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.check_low_stock_alert")
def check_low_stock_alert():
    """
    检查低库存并发送告警
    执行频率:每6小时
    """
    db = SessionLocal()
    
    try:
        logger.info("[ALERT] Checking low stock products...")
        
        # 查询低库存商品（使用当前运行时资产：mart.inventory_current）
        # 旧表 fact_inventory / dim_product 已不再作为运行时依赖，避免缺表导致 Postgres ERROR 日志刷屏。
        try:
            result = db.execute(
                text(
                    """
                    SELECT
                        platform_code,
                        shop_id,
                        platform_sku,
                        product_name,
                        available_stock,
                        safety_stock,
                        reorder_point
                    FROM mart.inventory_current
                    WHERE available_stock < safety_stock
                    ORDER BY (safety_stock - available_stock) DESC
                    LIMIT 50
                    """
                )
            )
        except Exception as query_err:
            # 如果 inventory 资产未部署（例如仅跑 Dashboard/BO），按“非关键任务”跳过，避免把错误当成系统故障。
            msg = str(query_err)
            if "does not exist" in msg or "UndefinedTable" in msg:
                logger.warning(f"[ALERT] inventory asset not available, skipped: {query_err}")
                return {"status": "skipped", "reason": "inventory_asset_missing"}
            raise
        
        low_stock_products = []
        for row in result:
            low_stock_products.append({
                "platform": row[0],
                "shop": row[1],
                "sku": row[2],
                "title": row[3],
                "available": row[4],
                "safety_stock": row[5],
                "shortage": row[5] - row[4]
            })
        
        if low_stock_products:
            logger.warning(f"[ALERT] Found {len(low_stock_products)} low stock products")
            # TODO: 发送钉钉/企业微信通知
            # send_dingtalk_notification(low_stock_products)
        else:
            logger.info("[OK] No low stock products found")
        
        return {
            "status": "success",
            "low_stock_count": len(low_stock_products),
            "products": low_stock_products
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to check low stock: {e}")
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.check_overdue_accounts_receivable")
def check_overdue_accounts_receivable():
    """
    检查应收账款逾期并更新状态
    执行频率:每天早上9点
    """
    db = SessionLocal()
    
    try:
        logger.info("[ALERT] Checking overdue accounts receivable...")

        def _is_missing_runtime_asset(exc: Exception) -> bool:
            message = str(exc)
            return "does not exist" in message or "UndefinedTable" in message
        
        # 更新逾期状态
        try:
            db.execute(text("""
                UPDATE fact_accounts_receivable
                SET 
                    is_overdue = TRUE,
                    overdue_days = CURRENT_DATE - due_date,
                    ar_status = 'overdue'
                WHERE due_date < CURRENT_DATE
                AND outstanding_amount_cny > 0
                AND ar_status != 'paid'
            """))
        except Exception as query_err:
            if _is_missing_runtime_asset(query_err):
                logger.warning(f"[ALERT] accounts receivable asset not available, skipped: {query_err}")
                db.rollback()
                return {"status": "skipped", "reason": "accounts_receivable_asset_missing"}
            raise
        db.commit()
        
        # 查询逾期账款
        try:
            result = db.execute(text("""
                SELECT
                    platform_code,
                    shop_id,
                    COUNT(*) as overdue_count,
                    SUM(outstanding_amount_cny) as total_overdue_amount
                FROM fact_accounts_receivable
                WHERE is_overdue = TRUE
                GROUP BY platform_code, shop_id
            """))
        except Exception as query_err:
            if _is_missing_runtime_asset(query_err):
                logger.warning(f"[ALERT] accounts receivable summary asset not available, skipped: {query_err}")
                db.rollback()
                return {"status": "skipped", "reason": "accounts_receivable_asset_missing"}
            raise
        
        overdue_summary = []
        for row in result:
            overdue_summary.append({
                "platform": row[0],
                "shop": row[1],
                "count": row[2],
                "amount": float(row[3])
            })
        
        if overdue_summary:
            total_overdue = sum(item['amount'] for item in overdue_summary)
            logger.warning(f"[ALERT] Overdue AR amount: CNY {total_overdue:,.2f}")
            # TODO: 发送通知
        else:
            logger.info("[OK] No overdue accounts receivable")
        
        return {
            "status": "success",
            "overdue_summary": overdue_summary
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to check overdue AR: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.auto_ingest_pending_files")
def auto_ingest_pending_files(max_files: int | None = None):
    """
    自动处理待入库文件(兜底机制)
    执行频率:每15分钟(由Celery Beat配置)
    
    v4.18.2优化:使用并发处理替代顺序处理,性能提升约5-10倍
    """
    db = SessionLocal()
    task_record_id = None
    lock_acquired = False
    try:
        max_files = max(1, int(max_files or _int_env("AUTO_INGEST_MAX_FILES_PER_RUN", AUTO_INGEST_MAX_FILES_PER_RUN)))
        stale_timeout_minutes = _int_env(
            "AUTO_INGEST_STALE_TIMEOUT_MINUTES",
            AUTO_INGEST_STALE_TIMEOUT_MINUTES,
        )
        lock_key = _int_env("AUTO_INGEST_LOCK_KEY", AUTO_INGEST_LOCK_KEY, minimum=1)
        lock_acquired = _acquire_auto_ingest_lock(db, lock_key)
        if not lock_acquired:
            logger.info("[AutoIngest] skipped because another auto-ingest task is running")
            return {"status": "skipped", "reason": "auto_ingest_already_running"}

        _recover_stale_auto_ingest_records(db, timeout_minutes=stale_timeout_minutes)

        pending_ids = db.execute(
            select(CatalogFile.id)
            .where(CatalogFile.status == 'pending')
            .order_by(CatalogFile.first_seen_at.asc())
            .limit(max_files)
        ).scalars().all()

        if not pending_ids:
            logger.info("[AutoIngest] 未发现待自动入库的文件")
            return {"status": "success", "processed": 0, "details": []}

        # v4.18.2优化:使用并发处理(类似手动同步)
        from backend.services.data_sync_service import DataSyncService
        
        # 预发布阶段优先稳定性，限制 auto-ingest 并发，避免 worker 被 OOM/SIGKILL。
        configured_max_concurrent = _int_env("AUTO_INGEST_MAX_CONCURRENT", AUTO_INGEST_MAX_CONCURRENT)
        max_concurrent = min(configured_max_concurrent, len(pending_ids))
        task_record_id = _create_auto_ingest_task_record(
            db,
            list(pending_ids),
            max_files,
            max_concurrent,
        )
        _heartbeat_auto_ingest_task(db, task_record_id)
        _claim_auto_ingest_files(db, list(pending_ids), task_record_id)
        progress_results: List[Dict[str, Any]] = []
        
        async def _process_ids_concurrent(ids: List[int]) -> List[Dict[str, Any]]:
            """并发处理文件(使用信号量控制并发数)
            
            v4.18.2更新:使用AsyncSessionLocal实现真异步数据库操作
            """
            semaphore = asyncio.Semaphore(max_concurrent)
            
            # v4.18.2更新:导入AsyncSessionLocal
            from backend.models.database import AsyncSessionLocal
            
            async def process_single(file_id: int) -> Dict[str, Any]:
                """带信号量的单文件处理"""
                async with semaphore:
                    # v4.18.2更新:使用异步会话(真异步)
                    db_local = AsyncSessionLocal()
                    try:
                        sync_service = DataSyncService(db_local)
                        readiness = await sync_service.get_file_sync_readiness(
                            file_id,
                            use_template_header_row=True,
                        )
                        if not readiness.get("should_auto_sync", True):
                            template_status = readiness.get("template_status")
                            if template_status == "update_required":
                                return {
                                    "success": False,
                                    "file_id": file_id,
                                    "file_name": readiness.get("file_name"),
                                    "status": "skipped",
                                    "error_code": "TEMPLATE_UPDATE_REQUIRED",
                                    "message": readiness.get("update_reason") or "模板需要更新后再同步",
                                }
                            if template_status == "missing":
                                return {
                                    "success": False,
                                    "file_id": file_id,
                                    "file_name": readiness.get("file_name"),
                                    "status": "skipped",
                                    "error_code": "NO_TEMPLATE",
                                    "message": readiness.get("message") or "无模板",
                                }
                        result = await sync_service.sync_single_file(
                            file_id=file_id,
                            only_with_template=True,
                            allow_quarantine=True,
                            task_id=task_record_id,
                        )
                        return result
                    except Exception as exc:
                        logger.error(
                            "[AutoIngest] 定时任务处理文件失败: file_id=%s, error=%s",
                            file_id,
                            exc,
                            exc_info=True,
                        )
                        try:
                            await db_local.rollback()
                        except Exception:
                            pass
                        return {
                            "success": False,
                            "file_id": file_id,
                            "status": "failed",
                            "message": str(exc),
                        }
                    finally:
                        try:
                            await db_local.close()
                        except Exception:
                            pass

            async def heartbeat_loop(stop_event: asyncio.Event):
                heartbeat_interval = _int_env(
                    "AUTO_INGEST_HEARTBEAT_INTERVAL_SECONDS",
                    AUTO_INGEST_HEARTBEAT_INTERVAL_SECONDS,
                )
                while not stop_event.is_set():
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval)
                    except asyncio.TimeoutError:
                        _heartbeat_auto_ingest_task(db, task_record_id)
             
            async def process_indexed(index: int, file_id: int):
                return index, await process_single(file_id)

            tasks = [
                asyncio.create_task(process_indexed(index, file_id))
                for index, file_id in enumerate(ids)
            ]
            processed_results = []
            stop_event = asyncio.Event()
            heartbeat_task = asyncio.create_task(heartbeat_loop(stop_event))
            try:
                for task in asyncio.as_completed(tasks):
                    i, result = await task
                    if isinstance(result, Exception):
                        processed_item = {
                            "success": False,
                            "file_id": ids[i],
                            "status": "failed",
                            "message": str(result),
                        }
                    else:
                        processed_item = result
                    processed_results.append(processed_item)
                    progress_results.append(processed_item)
                    _update_auto_ingest_task_progress(
                        db,
                        task_record_id,
                        len(ids),
                        progress_results,
                        max_files,
                        max_concurrent,
                        current_item=str(
                            processed_item.get("file_name")
                            or processed_item.get("file_id")
                            or ""
                        ),
                    )
            finally:
                stop_event.set()
                await heartbeat_task

            return processed_results

        logger.info(
            "[AutoIngest] 开始并发处理 %s 个文件(并发数=%s)",
            len(pending_ids),
            max_concurrent
        )
        
        reset_async_engine_pool_for_new_loop()
        results = asyncio.run(_process_ids_concurrent(pending_ids))

        if not progress_results:
            for idx in range(len(results)):
                progress_results.append(results[idx])
                _update_auto_ingest_task_progress(
                    db,
                    task_record_id,
                    len(results),
                    progress_results,
                    max_files,
                    max_concurrent,
                    current_item=str(
                        results[idx].get("file_name") or results[idx].get("file_id") or ""
                    ),
                )

        summary = _summarize_auto_ingest_results(results)

        logger.info(
            "[AutoIngest] 定时任务完成: processed=%s, success=%s, quarantined=%s, failed=%s, skipped=%s",
            summary["processed"],
            summary["succeeded"],
            summary["quarantined"],
            summary["failed"],
            summary["skipped"],
        )
        _complete_auto_ingest_task_record(
            db,
            task_record_id,
            summary,
            results,
            max_files=max_files,
            max_concurrent=max_concurrent,
        )

        return {
            "status": "success",
            "summary": summary,
            "details": results,
        }

    except Exception as exc:  # noqa: BLE001
        _fail_auto_ingest_task_record(db, task_record_id, exc)
        logger.error(f"[AutoIngest] 定时任务执行失败: {exc}", exc_info=True)
        return {"status": "failed", "error": str(exc)}
    finally:
        if lock_acquired:
            try:
                _release_auto_ingest_lock(db, _int_env("AUTO_INGEST_LOCK_KEY", AUTO_INGEST_LOCK_KEY, minimum=1))
            except Exception as unlock_exc:  # noqa: BLE001
                logger.warning("[AutoIngest] failed to release advisory lock: %s", unlock_exc)
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.verify_backup")
def verify_backup():
    """
    [*] Phase 2.2: 备份验证任务(业务层)
    验证最新备份的完整性
    执行频率:每天凌晨 4:00(备份后 1 小时)
    
    注意:系统级全量备份由宿主机 cron/systemd 负责(scripts/backup_all.sh)
    此任务仅用于验证备份状态,不执行实际备份
    """
    import subprocess
    from pathlib import Path
    
    try:
        logger.info("[BACKUP] Verifying latest backup...")
        
        # 查找最新备份目录
        backup_base = Path(root_dir) / "backups"
        if not backup_base.exists():
            logger.warning("[BACKUP] Backup directory not found")
            return {"status": "skipped", "reason": "backup_directory_not_found"}
        
        # 查找最新备份
        backup_dirs = sorted(backup_base.glob("backup_*"), reverse=True)
        if not backup_dirs:
            logger.warning("[BACKUP] No backup found")
            return {"status": "skipped", "reason": "no_backup_found"}
        
        latest_backup = backup_dirs[0]
        logger.info(f"[BACKUP] Verifying backup: {latest_backup}")
        
        # 调用验证脚本(通过 subprocess,不直接执行备份逻辑)
        verify_script = root_dir / "scripts" / "verify_backup.sh"
        if not verify_script.exists():
            logger.warning("[BACKUP] Verify script not found")
            return {"status": "skipped", "reason": "verify_script_not_found"}
        
        result = subprocess.run(
            ["bash", str(verify_script), str(latest_backup)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            logger.info(f"[OK] Backup verification passed: {latest_backup}")
            return {"status": "success", "backup_dir": str(latest_backup)}
        else:
            logger.error(f"[ERROR] Backup verification failed: {result.stderr}")
            # TODO: 发送告警通知
            return {"status": "failed", "error": result.stderr, "backup_dir": str(latest_backup)}
            
    except Exception as e:
        logger.error(f"[ERROR] Backup verification task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="backend.tasks.scheduled_tasks.cleanup_old_backups")
def cleanup_old_backups(retention_days: int = 30):
    """
    [*] Phase 2.2: 备份清理任务(业务层)
    按保留策略删除旧备份
    执行频率:每天凌晨 5:00
    
    注意:系统级全量备份由宿主机 cron/systemd 负责
    此任务仅用于清理旧备份,不执行实际备份
    """
    from pathlib import Path
    from datetime import datetime, timedelta
    
    try:
        logger.info(f"[BACKUP] Cleaning up backups older than {retention_days} days...")
        
        backup_base = Path(root_dir) / "backups"
        if not backup_base.exists():
            logger.warning("[BACKUP] Backup directory not found")
            return {"status": "skipped", "reason": "backup_directory_not_found"}
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        deleted_size = 0
        
        # 查找并删除旧备份
        for backup_dir in backup_base.glob("backup_*"):
            if not backup_dir.is_dir():
                continue
            
            # 从目录名提取时间戳(backup_YYYYMMDD_HHMMSS)
            try:
                timestamp_str = backup_dir.name.replace("backup_", "")
                backup_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                
                if backup_date < cutoff_date:
                    # 计算目录大小
                    dir_size = sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
                    deleted_size += dir_size
                    
                    # 删除目录
                    import shutil
                    shutil.rmtree(backup_dir)
                    deleted_count += 1
                    logger.info(f"[BACKUP] Deleted old backup: {backup_dir.name}")
            except (ValueError, OSError) as e:
                logger.warning(f"[BACKUP] Failed to process backup directory {backup_dir}: {e}")
                continue
        
        if deleted_count > 0:
            deleted_size_mb = deleted_size / (1024 * 1024)
            logger.info(
                f"[OK] Cleanup completed: deleted {deleted_count} backups, "
                f"freed {deleted_size_mb:.2f} MB"
            )
        else:
            logger.info("[OK] No old backups to clean up")
        
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "freed_size_mb": round(deleted_size / (1024 * 1024), 2)
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Backup cleanup task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="backend.tasks.scheduled_tasks.trigger_system_backup")
def trigger_system_backup():
    """
    [*] Phase 2.2: 触发系统级备份(业务层)
    通过 subprocess 间接调用统一备份脚本(不直接执行备份逻辑)
    执行频率:按需(手动触发或特殊场景)
    
    注意:
    - 系统级全量备份主要由宿主机 cron/systemd 负责(scripts/backup_all.sh)
    - 此任务仅用于应用层触发系统级备份的场景
    - 不直接执行 pg_dump 等命令,而是调用统一备份脚本
    """
    import subprocess
    
    try:
        logger.info("[BACKUP] Triggering system backup from application layer...")
        
        # 调用统一备份脚本(通过 subprocess)
        backup_script = root_dir / "scripts" / "backup_all.sh"
        if not backup_script.exists():
            logger.error("[BACKUP] Backup script not found")
            return {"status": "failed", "error": "backup_script_not_found"}
        
        result = subprocess.run(
            ["bash", str(backup_script)],
            capture_output=True,
            text=True,
            timeout=3600,  # 1 小时超时
            cwd=str(root_dir)
        )
        
        if result.returncode == 0:
            logger.info("[OK] System backup triggered successfully")
            return {"status": "success", "output": result.stdout}
        else:
            logger.error(f"[ERROR] System backup failed: {result.stderr}")
            # TODO: 发送告警通知
            return {"status": "failed", "error": result.stderr}
            
    except subprocess.TimeoutExpired:
        logger.error("[ERROR] System backup timeout (exceeded 1 hour)")
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        logger.error(f"[ERROR] System backup task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="backend.tasks.scheduled_tasks.backup_database")
def backup_database():
    """Backward-compatible alias for historical beat entries."""
    return trigger_system_backup()
