"""
数据同步 Celery 任务模块

⭐ v4.19.1 恢复：使用 Celery 任务队列执行数据同步
- 任务持久化：任务存储在 Redis 中，服务器重启后自动恢复
- 资源隔离：任务在独立的 Celery worker 进程中执行，不影响 API 服务
- 水平扩展：可以通过增加 worker 来扩展处理能力

注意：
- 使用 asyncio.run() 包装异步逻辑（避免多次调用）
- Celery worker 并发控制（进程级）和内部 Semaphore（协程级）是不同层次的并发控制
- 仅对网络/超时错误重试，业务逻辑错误不重试
"""

from backend.celery_app import celery_app
from typing import List
import asyncio
from modules.core.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name='data_sync.sync_single_file',
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1分钟
    queue='data_sync',
    priority=5,  # 中等优先级
    time_limit=1800,  # 30分钟硬超时
    soft_time_limit=1500  # 25分钟软超时
)
def sync_single_file_task(
    self,
    file_id: int,
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,
    user_id: int = None  # ⭐ Phase 4.2: 用户ID（可选，用于配额管理）
):
    """
    单文件同步 Celery 任务
    
    使用 asyncio.run() 包装整个异步逻辑：
    - 避免多次调用 asyncio.run() 创建多个事件循环
    - 正确处理异步数据库会话的关闭
    
    Args:
        self: Celery 任务实例（bind=True）
        file_id: 文件ID
        task_id: 任务ID
        only_with_template: 仅同步有模板的文件
        allow_quarantine: 允许隔离
        use_template_header_row: 使用模板表头行
    """
    async def _async_task():
        """内部异步函数，执行实际的同步逻辑"""
        from backend.services.data_sync_service import DataSyncService
        from backend.services.sync_progress_tracker import SyncProgressTracker
        from backend.models.database import AsyncSessionLocal
        
        db = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db)
        
        try:
            logger.info(f"[CeleryTask] 开始单文件同步 file_id={file_id}, task_id={task_id}")
            
            # ⭐ 修复：检查进度任务是否已存在（API层可能已创建）
            existing_task = await progress_tracker.get_task(task_id)
            if not existing_task:
                # 如果不存在，则创建进度任务（降级模式或API层未创建的情况）
                await progress_tracker.create_task(
                    task_id=task_id,
                    task_type="single_file",
                    total_files=1
                )
            # 更新状态为processing（无论是否新创建）
            await progress_tracker.update_task(task_id, {"status": "processing"})
            
            # 执行同步
            sync_service = DataSyncService(db)
            result = await sync_service.sync_single_file(
                file_id=file_id,
                only_with_template=only_with_template,
                allow_quarantine=allow_quarantine,
                task_id=task_id,
                use_template_header_row=use_template_header_row
            )
            
            # 更新进度
            if result.get('success', False):
                await progress_tracker.update_task(task_id, {
                    "processed_files": 1,
                    "current_file": result.get('file_name', ''),
                    "file_progress": 100.0
                })
                await progress_tracker.complete_task(task_id, success=True)
                logger.info(f"[CeleryTask] 单文件同步成功 file_id={file_id}, task_id={task_id}")
            else:
                error_msg = result.get('message', '同步失败')
                await progress_tracker.update_task(task_id, {
                    "processed_files": 1,
                    "current_file": result.get('file_name', ''),
                    "file_progress": 100.0
                })
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
                logger.warning(f"[CeleryTask] 单文件同步失败 file_id={file_id}, task_id={task_id}, message={error_msg}")
            
            return result
            
        except Exception as e:
            # 记录错误
            logger.error(f"[CeleryTask] 单文件同步异常 file_id={file_id}, task_id={task_id}: {e}", exc_info=True)
            try:
                error_msg = str(e)
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
            except Exception:
                pass
            # 重新抛出异常，让外层处理重试逻辑
            raise
        finally:
            # ⭐ Phase 4.2: 减少用户任务计数（任务完成或失败时）
            if user_id:
                try:
                    from backend.services.user_task_quota import get_user_task_quota_service
                    quota_service = get_user_task_quota_service()
                    # ⭐ 修复：在异步函数内部，可以直接使用 await
                    await quota_service.decrement_user_task_count(user_id)
                except Exception as quota_error:
                    logger.warning(f"[CeleryTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
            
            # 正确关闭异步数据库会话
            try:
                await db.close()
            except Exception:
                pass
    
    # 在同步函数中运行异步代码
    try:
        result = asyncio.run(_async_task())
        return result
    except Exception as exc:
        # ⭐ Phase 4.2: 任务异常时也要减少用户任务计数
        if user_id:
            try:
                from backend.services.user_task_quota import get_user_task_quota_service
                quota_service = get_user_task_quota_service()
                # ⭐ 修复：在同步函数中使用 asyncio.run() 执行异步代码
                asyncio.run(quota_service.decrement_user_task_count(user_id))
            except Exception as quota_error:
                logger.warning(f"[CeleryTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
        
        # 记录错误
        logger.error(f"[CeleryTask] 单文件同步失败 file_id={file_id}, task_id={task_id}: {exc}", exc_info=True)
        
        # 重试逻辑：仅对可重试的错误进行重试
        if isinstance(exc, (ConnectionError, TimeoutError)):
            # 网络错误、超时错误，可以重试
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))  # 指数退避
        else:
            # 业务逻辑错误（文件不存在、模板不匹配等），不重试
            # 任务已经通过 _async_task 更新了进度和状态，直接返回错误结果
            return {
                'success': False,
                'file_id': file_id,
                'status': 'failed',
                'message': str(exc)
            }


@celery_app.task(
    name='data_sync.sync_batch',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue='data_sync',
    priority=5,
    time_limit=1800,  # 30分钟硬超时
    soft_time_limit=1500  # 25分钟软超时
)
def sync_batch_task(
    self,
    file_ids: List[int],
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,
    max_concurrent: int = 10,
    user_id: int = None  # ⭐ Phase 4.2: 用户ID（可选，用于配额管理）
):
    """
    批量同步 Celery 任务
    
    使用 asyncio.run() 包装整个异步逻辑：
    - 批量同步内部使用 asyncio.Semaphore 控制并发（不冲突，因为是在单个任务内部）
    - Celery worker 并发控制：限制 worker 进程中的并发任务数
    - 内部 Semaphore：限制单个批量任务内部的并发文件处理数
    
    注意：
    - Celery worker 并发数（worker_concurrency=4）：每个 worker 最多同时处理 4 个任务
    - 批量任务内部并发数（max_concurrent=10）：每个批量任务内部最多同时处理 10 个文件
    - 两者不冲突，合理配置可以充分利用资源
    """
    async def _async_task():
        """内部异步函数，执行实际的批量同步逻辑"""
        from backend.services.data_sync_service import DataSyncService
        from backend.services.sync_progress_tracker import SyncProgressTracker
        from backend.models.database import AsyncSessionLocal
        from datetime import datetime, timezone
        from sqlalchemy import select
        from modules.core.db import CatalogFile
        
        db_main = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db_main)
        
        # 任务超时保护（默认30分钟）
        TASK_TIMEOUT_SECONDS = 30 * 60
        task_start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(f"[CeleryTask] 开始批量同步 {len(file_ids)} 个文件, task_id={task_id}")
            
            # ⭐ 修复：检查进度任务是否已存在（API层可能已创建）
            existing_task = await progress_tracker.get_task(task_id)
            if not existing_task:
                # 如果不存在，则创建进度任务（降级模式或API层未创建的情况）
                await progress_tracker.create_task(
                    task_id=task_id,
                    task_type="bulk_ingest",
                    total_files=len(file_ids)
                )
            # 更新状态为processing（无论是否新创建）
            await progress_tracker.update_task(task_id, {"status": "processing"})
            
            # 并发控制（使用信号量限制并发数）
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def sync_file_with_semaphore(fid: int):
                """带信号量的文件同步"""
                async with semaphore:
                    db = AsyncSessionLocal()
                    try:
                        sync_service = DataSyncService(db)
                        result = await sync_service.sync_single_file(
                            file_id=fid,
                            only_with_template=only_with_template,
                            allow_quarantine=allow_quarantine,
                            task_id=task_id,
                            use_template_header_row=use_template_header_row
                        )
                        return result
                    except Exception as e:
                        logger.error(f"[CeleryTask] 文件{fid}同步异常: {e}", exc_info=True)
                        try:
                            await db.rollback()
                        except Exception:
                            pass
                        return {
                            'success': False,
                            'file_id': fid,
                            'status': 'failed',
                            'message': f'同步异常: {str(e)}'
                        }
                    finally:
                        try:
                            await db.close()
                        except Exception:
                            pass
            
            # 批量处理文件（异步并发）
            tasks = [sync_file_with_semaphore(fid) for fid in file_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            processed_files = 0
            success_files = 0
            failed_files = 0
            skipped_files = 0
            
            for i, result in enumerate(results):
                fid = file_ids[i]
                
                if isinstance(result, Exception):
                    processed_files += 1
                    failed_files += 1
                    error_msg = f"文件{fid}同步异常: {str(result)}"
                    await progress_tracker.add_error(task_id, error_msg)
                else:
                    processed_files += 1
                    status = result.get("status", "")
                    if result.get("success"):
                        success_files += 1
                    elif status == "skipped":
                        skipped_files += 1
                    else:
                        failed_files += 1
                        error_msg = result.get('message', '同步失败')
                        await progress_tracker.add_error(task_id, f"文件{fid}: {error_msg}")
                
                # 更新进度
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "status": "processing"
                })
            
            # 超时检查函数
            def check_timeout():
                """检查任务是否超时"""
                task_elapsed = (datetime.now(timezone.utc) - task_start_time).total_seconds()
                return task_elapsed > TASK_TIMEOUT_SECONDS
            
            # 数据质量Gate（批量同步完成后自动质量检查）
            quality_check_result = None
            if not check_timeout():
                try:
                    # 查询成功文件
                    success_file_ids = [
                        fid for i, fid in enumerate(file_ids) 
                        if not isinstance(results[i], Exception) and results[i].get("success")
                    ]
                    
                    if success_file_ids:
                        result_query = await db_main.execute(
                            select(CatalogFile).where(CatalogFile.id.in_(success_file_ids))
                        )
                        successful_files = result_query.scalars().all()
                    else:
                        successful_files = []
                    
                    # 质量检查（使用run_in_executor包装同步调用）
                    if successful_files:
                        # 按平台+店铺分组
                        platform_shops = {}
                        for file_record in successful_files:
                            key = f"{file_record.platform_code}_{file_record.shop_id or 'default'}"
                            if key not in platform_shops:
                                platform_shops[key] = {
                                    "platform_code": file_record.platform_code,
                                    "shop_id": file_record.shop_id
                                }
                        
                        # 同步质量检查函数（在executor中执行）
                        def _sync_quality_check(platform_shops_dict):
                            """同步质量检查函数"""
                            # 在函数内部导入必要的模块（因为函数在run_in_executor中执行）
                            from backend.models.database import SessionLocal
                            from backend.services.c_class_data_validator import get_c_class_data_validator
                            from datetime import datetime, timezone as tz
                            from modules.core.logger import get_logger as get_log
                            
                            log = get_log(__name__)
                            db_quality = SessionLocal()
                            try:
                                validator = get_c_class_data_validator(db_quality)
                                quality_scores = []
                                missing_fields_list = []
                                
                                for key, info in platform_shops_dict.items():
                                    try:
                                        check_result = validator.check_b_class_completeness(
                                            platform_code=info["platform_code"],
                                            shop_id=info["shop_id"],
                                            metric_date=datetime.now(tz.utc).date()
                                        )
                                        
                                        if check_result and not check_result.get("error"):
                                            quality_scores.append(check_result.get("data_quality_score", 0))
                                            # 使用正确的字段名（check_b_class_completeness 返回的是 missing_fields）
                                            mf = check_result.get("missing_fields", [])
                                            if mf:
                                                missing_fields_list.extend(mf)
                                    except Exception as check_error:
                                        log.warning(f"[CeleryTask] 平台{info['platform_code']}质量检查失败: {check_error}")
                                        try:
                                            db_quality.rollback()
                                        except Exception:
                                            pass
                                
                                return {
                                    "quality_scores": quality_scores,
                                    "missing_fields_list": missing_fields_list
                                }
                            finally:
                                db_quality.close()
                        
                        # 使用run_in_executor执行同步质量检查
                        loop = asyncio.get_running_loop()
                        quality_result = await loop.run_in_executor(None, _sync_quality_check, platform_shops)
                        
                        quality_scores = quality_result["quality_scores"]
                        missing_fields_list = quality_result["missing_fields_list"]
                        
                        # 计算平均质量评分
                        avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
                        
                        quality_check_result = {
                            "avg_quality_score": round(avg_quality_score, 2),
                            "checked_platforms": len(platform_shops),
                            "missing_fields": list(set(missing_fields_list)),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        
                        # 保存质量检查结果到任务详情
                        await progress_tracker.update_task(task_id, {
                            "task_details": {
                                "quality_check": quality_check_result
                            }
                        })
                        
                        logger.info(f"[CeleryTask] 数据质量检查完成: 平均评分={avg_quality_score:.2f}")
                except Exception as e:
                    logger.warning(f"[CeleryTask] 数据质量检查失败: {e}", exc_info=True)
                    # 质量检查失败不影响同步结果
            
            # 检查是否因超时失败
            task_elapsed = (datetime.now(timezone.utc) - task_start_time).total_seconds()
            if task_elapsed > TASK_TIMEOUT_SECONDS:
                completion_message = f"任务超时（已运行{task_elapsed:.1f}秒，超过限制{TASK_TIMEOUT_SECONDS}秒）: 成功{success_files}个，失败{failed_files}个"
                logger.warning(f"[CeleryTask] {completion_message}")
                await progress_tracker.complete_task(
                    task_id,
                    success=False,
                    error=completion_message
                )
            else:
                # 构建完成消息（包含跳过文件数）
                if skipped_files > 0:
                    completion_message = f"成功{success_files}个，失败{failed_files}个，跳过{skipped_files}个"
                else:
                    completion_message = f"成功{success_files}个，失败{failed_files}个"
                
                await progress_tracker.complete_task(
                    task_id,
                    success=(failed_files == 0),
                    error=None if failed_files == 0 else completion_message
                )
                logger.info(f"[CeleryTask] 批量同步完成: {completion_message}（耗时{task_elapsed:.1f}秒）")
            
            return {
                'success': failed_files == 0,
                'processed_files': processed_files,
                'success_files': success_files,
                'failed_files': failed_files,
                'skipped_files': skipped_files
            }
            
        except Exception as e:
            logger.error(f"[CeleryTask] 批量同步异常 task_id={task_id}: {e}", exc_info=True)
            try:
                error_msg = str(e)
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
            except Exception:
                pass
            raise
        finally:
            # ⭐ Phase 4.2: 减少用户任务计数（任务完成或失败时）
            if user_id:
                try:
                    from backend.services.user_task_quota import get_user_task_quota_service
                    quota_service = get_user_task_quota_service()
                    # ⭐ 修复：在异步函数内部，可以直接使用 await
                    await quota_service.decrement_user_task_count(user_id)
                except Exception as quota_error:
                    logger.warning(f"[CeleryTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
            
            try:
                await db_main.close()
            except Exception:
                pass
    
    # 在同步函数中运行异步代码
    try:
        result = asyncio.run(_async_task())
        return result
    except Exception as exc:
        # ⭐ Phase 4.2: 任务异常时也要减少用户任务计数
        if user_id:
            try:
                from backend.services.user_task_quota import get_user_task_quota_service
                quota_service = get_user_task_quota_service()
                # ⭐ 修复：在同步函数中使用 asyncio.run() 执行异步代码
                asyncio.run(quota_service.decrement_user_task_count(user_id))
            except Exception as quota_error:
                logger.warning(f"[CeleryTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
        # 记录错误
        logger.error(f"[CeleryTask] 批量同步失败 task_id={task_id}: {exc}", exc_info=True)
        
        # 重试逻辑：仅对可重试的错误进行重试
        if isinstance(exc, (ConnectionError, TimeoutError)):
            # 网络错误、超时错误，可以重试
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))  # 指数退避
        else:
            # 业务逻辑错误，不重试
            return {
                'success': False,
                'task_id': task_id,
                'status': 'failed',
                'message': str(exc)
            }

