"""
定时任务 - Celery Beat定时执行的任务
包含：物化视图刷新、库存告警、应收账款检查、数据库备份
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到Python路径
from modules.core.path_manager import get_project_root
root_dir = get_project_root()
sys.path.insert(0, str(root_dir))

from backend.celery_app import celery_app
from backend.models.database import SessionLocal
from backend.services.auto_ingest_orchestrator import AutoIngestOrchestrator
from modules.core.db import CatalogFile
from sqlalchemy import select, text
import logging

logger = logging.getLogger(__name__)

AUTO_INGEST_MAX_FILES_PER_RUN = 50


@celery_app.task(name="backend.tasks.scheduled_tasks.refresh_sales_materialized_views")
def refresh_sales_materialized_views():
    """
    刷新销售相关物化视图
    执行频率：每5分钟
    性能：增量刷新（CONCURRENTLY），不锁表
    """
    db = SessionLocal()
    
    try:
        logger.info("[REFRESH] Starting to refresh sales materialized views...")
        
        # 刷新日度销售视图
        logger.info("  Refreshing mv_daily_sales...")
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales"))
        db.commit()
        
        # 刷新周度销售视图（依赖日度视图）
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
    执行频率：每10分钟
    """
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
    执行频率：每6小时
    """
    db = SessionLocal()
    
    try:
        logger.info("[ALERT] Checking low stock products...")
        
        # 查询低库存商品
        result = db.execute(text("""
            SELECT
                i.platform_code,
                i.shop_id,
                p.platform_sku,
                p.title,
                i.quantity_available,
                i.safety_stock,
                i.reorder_point
            FROM fact_inventory i
            JOIN dim_product p ON i.product_id = p.product_surrogate_id
            WHERE i.quantity_available < i.safety_stock
            ORDER BY (i.safety_stock - i.quantity_available) DESC
            LIMIT 50
        """))
        
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
    执行频率：每天早上9点
    """
    db = SessionLocal()
    
    try:
        logger.info("[ALERT] Checking overdue accounts receivable...")
        
        # 更新逾期状态
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
        db.commit()
        
        # 查询逾期账款
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
def auto_ingest_pending_files(max_files: int = AUTO_INGEST_MAX_FILES_PER_RUN):
    """
    自动处理待入库文件（兜底机制）
    执行频率：每15分钟（由Celery Beat配置）
    
    v4.18.2优化：使用并发处理替代顺序处理，性能提升约5-10倍
    """
    db = SessionLocal()
    try:
        pending_ids = db.execute(
            select(CatalogFile.id)
            .where(CatalogFile.status == 'pending')
            .order_by(CatalogFile.first_seen_at.asc())
            .limit(max_files)
        ).scalars().all()

        if not pending_ids:
            logger.info("[AutoIngest] 未发现待自动入库的文件")
            return {"status": "success", "processed": 0, "details": []}

        # v4.18.2优化：使用并发处理（类似手动同步）
        from backend.services.data_sync_service import DataSyncService
        
        # 动态调整并发数：5-20之间，根据文件数量
        max_concurrent = min(20, max(5, len(pending_ids) // 10 + 1))
        
        async def _process_ids_concurrent(ids: List[int]) -> List[Dict[str, Any]]:
            """并发处理文件（使用信号量控制并发数）
            
            v4.18.2更新：使用AsyncSessionLocal实现真异步数据库操作
            """
            semaphore = asyncio.Semaphore(max_concurrent)
            
            # v4.18.2更新：导入AsyncSessionLocal
            from backend.models.database import AsyncSessionLocal
            
            async def process_single(file_id: int) -> Dict[str, Any]:
                """带信号量的单文件处理"""
                async with semaphore:
                    # v4.18.2更新：使用异步会话（真异步）
                    db_local = AsyncSessionLocal()
                    try:
                        sync_service = DataSyncService(db_local)
                        result = await sync_service.sync_single_file(
                            file_id=file_id,
                            only_with_template=True,
                            allow_quarantine=True
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
            
            # 并发执行所有任务
            tasks = [process_single(file_id) for file_id in ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理异常结果
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "success": False,
                        "file_id": ids[i],
                        "status": "failed",
                        "message": str(result),
                    })
                else:
                    processed_results.append(result)
            
            return processed_results

        logger.info(
            "[AutoIngest] 开始并发处理 %s 个文件（并发数=%s）",
            len(pending_ids),
            max_concurrent
        )
        
        results = asyncio.run(_process_ids_concurrent(pending_ids))

        summary = {
            "processed": len(results),
            "succeeded": 0,
            "quarantined": 0,
            "failed": 0,
            "skipped": 0,
            "skipped_no_template": 0,
        }

        for item in results:
            status = item.get("status")
            if status == "success":
                summary["succeeded"] += 1
            elif status == "quarantined":
                summary["quarantined"] += 1
            elif status == "failed":
                summary["failed"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
                message = item.get("message", "")
                message_lower = message.lower()
                if (
                    "no_template" in message_lower
                    or "no template" in message_lower
                    or "无模板" in message
                ):
                    summary["skipped_no_template"] += 1

        logger.info(
            "[AutoIngest] 定时任务完成: processed=%s, success=%s, quarantined=%s, failed=%s, skipped=%s",
            summary["processed"],
            summary["succeeded"],
            summary["quarantined"],
            summary["failed"],
            summary["skipped"],
        )

        return {
            "status": "success",
            "summary": summary,
            "details": results,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(f"[AutoIngest] 定时任务执行失败: {exc}", exc_info=True)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.verify_backup")
def verify_backup():
    """
    ⭐ Phase 2.2: 备份验证任务（业务层）
    验证最新备份的完整性
    执行频率：每天凌晨 4:00（备份后 1 小时）
    
    注意：系统级全量备份由宿主机 cron/systemd 负责（scripts/backup_all.sh）
    此任务仅用于验证备份状态，不执行实际备份
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
        
        # 调用验证脚本（通过 subprocess，不直接执行备份逻辑）
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
    ⭐ Phase 2.2: 备份清理任务（业务层）
    按保留策略删除旧备份
    执行频率：每天凌晨 5:00
    
    注意：系统级全量备份由宿主机 cron/systemd 负责
    此任务仅用于清理旧备份，不执行实际备份
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
            
            # 从目录名提取时间戳（backup_YYYYMMDD_HHMMSS）
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
    ⭐ Phase 2.2: 触发系统级备份（业务层）
    通过 subprocess 间接调用统一备份脚本（不直接执行备份逻辑）
    执行频率：按需（手动触发或特殊场景）
    
    注意：
    - 系统级全量备份主要由宿主机 cron/systemd 负责（scripts/backup_all.sh）
    - 此任务仅用于应用层触发系统级备份的场景
    - 不直接执行 pg_dump 等命令，而是调用统一备份脚本
    """
    import subprocess
    
    try:
        logger.info("[BACKUP] Triggering system backup from application layer...")
        
        # 调用统一备份脚本（通过 subprocess）
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

