# 技术设计：恢复 Celery 任务队列

## 上下文

当前系统使用 `asyncio.create_task()` 在内存中执行数据同步任务，存在以下问题：
1. 服务器重启后任务丢失
2. 资源隔离不足，一个用户的任务可能影响其他用户
3. 无法水平扩展

## 目标

1. **任务持久化**：任务存储在 Redis 中，服务器重启后自动恢复
2. **资源隔离**：任务在独立的 Celery worker 进程中执行，不影响 API 服务
3. **水平扩展**：可以通过增加 worker 来扩展处理能力
4. **用户隔离**：实现用户级别的任务数量限制

## 非目标

1. **不迁移定时任务**：定时任务已使用 Celery，保持不变
2. **不改变 API 接口**：保持现有 API 响应格式不变
3. **不改变进度跟踪**：继续使用 `SyncProgressTracker` 和 `SyncProgressTask` 表

## 关键决策

### 决策 1：使用 Celery 而不是其他任务队列

**选项 A：Celery + Redis**
- ✅ 已有基础设施（Celery 配置、Redis 部署）
- ✅ 成熟稳定，社区支持好
- ✅ 支持任务持久化、重试、优先级
- ❌ 需要额外的 worker 进程

**选项 B：RQ (Redis Queue)**
- ✅ 更轻量级
- ❌ 功能较少，不支持任务优先级
- ❌ 需要重新学习和部署

**选项 C：保持现状（asyncio.create_task）**
- ✅ 无需额外服务
- ❌ 无法持久化
- ❌ 无法水平扩展

**决策**：选择选项 A（Celery + Redis），因为已有基础设施，且功能完善。

### 决策 2：任务序列化方式

**选项 A：JSON 序列化**
- ✅ 可读性好，易于调试
- ✅ 跨语言兼容
- ❌ 不支持复杂对象（需要手动转换）

**选项 B：Pickle 序列化**
- ✅ 支持复杂对象
- ❌ 安全性问题（反序列化可能执行恶意代码）
- ❌ 跨语言不兼容

**决策**：选择选项 A（JSON 序列化），因为数据同步任务的参数都是简单类型（file_id, task_id 等），不需要复杂对象。

### 决策 3：任务重试策略

**策略**：
- 默认重试 3 次
- 重试间隔：指数退避（1秒、2秒、4秒）
- 仅对特定错误重试（网络错误、临时数据库错误）
- 不重试业务逻辑错误（文件不存在、模板不匹配等）

### 决策 4：并发控制

**当前**：使用 `asyncio.Semaphore(10)` 控制并发

**迁移后**：
- **Celery worker 并发控制**：`worker_concurrency=4`（每个 worker 最多同时处理 4 个任务）
  - 作用：限制 worker 进程中的并发任务数，防止资源耗尽
  - 如果有 2 个 worker，总并发任务数为 8
  - 可以通过增加 worker 来扩展并发能力

- **批量任务内部并发控制**：`asyncio.Semaphore(max_concurrent=10)`（每个批量任务内部最多同时处理 10 个文件）
  - 作用：限制单个批量任务内部的并发文件处理数，防止单个任务占用过多资源
  - 与 Celery worker 并发控制不冲突，两者是不同层次的并发控制

**并发控制层次说明**：
```
Celery Worker 层（进程级）：
  - worker_concurrency=4：每个 worker 最多同时处理 4 个任务
  - 2 个 worker = 最多 8 个并发任务

批量任务内部层（协程级）：
  - max_concurrent=10：每个批量任务内部最多同时处理 10 个文件
  - 如果 8 个并发任务都是批量任务，理论上最多 80 个并发文件处理
  - 但实际受限于数据库连接池大小和 CPU 资源
```

**任务队列配置**：
- `data_sync` 队列：用于数据同步任务
- `data_processing` 队列：用于 Excel 处理（已存在）
- `scheduled` 队列：用于定时任务（已存在）

**推荐配置**：
- Celery worker 并发数：`worker_concurrency=4`（根据 CPU 核心数调整）
  - **配置方式1**：在 `backend/celery_app.py` 中设置 `celery_app.conf.worker_concurrency=4`
  - **配置方式2**：启动命令中使用 `--concurrency=4` 参数（优先级更高）
  - **示例**：`celery -A backend.celery_app worker --loglevel=info --queues=data_sync --concurrency=4`
- 批量任务内部并发数：`max_concurrent=10`（根据数据库连接池大小调整）
- 数据库连接池：`pool_size=30, max_overflow=20`（确保有足够的连接）

## 架构设计

### 数据流

```
1. 用户提交同步请求
   ↓
2. FastAPI 路由接收请求
   ↓
3. 创建进度任务（SyncProgressTask 表）
   ↓
4. 提交 Celery 任务到 Redis
   ↓
5. 立即返回 task_id 给前端
   ↓
6. Celery Worker 从 Redis 获取任务
   ↓
7. 执行同步任务（DataSyncService）
   ↓
8. 更新进度（SyncProgressTracker）
   ↓
9. 完成任务，更新状态
```

### 任务定义

```python
# backend/tasks/data_sync_tasks.py

from backend.celery_app import celery_app  # ⭐ 修复：使用与现有代码一致的导入方式
from typing import List
from backend.services.data_sync_service import DataSyncService
from backend.services.sync_progress_tracker import SyncProgressTracker
from backend.models.database import AsyncSessionLocal
import asyncio
from modules.core.logger import get_logger

logger = get_logger(__name__)

@celery_app.task(  # ⭐ 修复：使用与现有代码一致的装饰器
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
    use_template_header_row: bool = True
):
    """
    单文件同步 Celery 任务
    
    ⭐ 修复：正确调用异步函数的方式
    - 使用 asyncio.run() 包装整个异步逻辑
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
        db = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db)
        
        try:
            # 创建进度任务
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
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
            else:
                error_msg = result.get('message', '同步失败')
                await progress_tracker.update_task(task_id, {
                    "processed_files": 1,
                    "current_file": result.get('file_name', ''),
                    "file_progress": 100.0
                })
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
            
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
            # ⭐ 修复：正确关闭异步数据库会话
            try:
                await db.close()
            except Exception:
                pass
    
    # 在同步函数中运行异步代码
    try:
        result = asyncio.run(_async_task())
        return result
    except Exception as exc:
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


@celery_app.task(  # ⭐ 修复：使用与现有代码一致的装饰器
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
    max_concurrent: int = 10
):
    """
    批量同步 Celery 任务
    
    ⭐ 修复：正确调用异步函数的方式
    - 使用 asyncio.run() 包装整个异步逻辑
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
        # 实现逻辑类似 process_batch_sync_background
        # 但使用 asyncio.run() 包装，确保在 Celery worker 中正确执行
        from backend.services.data_sync_service import DataSyncService
        from backend.services.sync_progress_tracker import SyncProgressTracker
        from backend.models.database import AsyncSessionLocal
        from datetime import datetime, timezone
        from sqlalchemy import select
        from modules.core.db import CatalogFile
        
        db_main = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db_main)
        
        # 任务超时保护（默认30分钟）
        # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致
        TASK_TIMEOUT_SECONDS = 30 * 60
        task_start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(f"[CeleryTask] 开始批量同步 {len(file_ids)} 个文件, task_id={task_id}")
            
            # 创建进度任务
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="bulk_ingest",
                total_files=len(file_ids)
            )
            await progress_tracker.update_task(task_id, {"status": "processing"})
            
            # 并发控制（使用信号量限制并发数）
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def sync_file_with_semaphore(file_id: int):
                """带信号量的文件同步"""
                async with semaphore:
                    db = AsyncSessionLocal()
                    try:
                        sync_service = DataSyncService(db)
                        result = await sync_service.sync_single_file(
                            file_id=file_id,
                            only_with_template=only_with_template,
                            allow_quarantine=allow_quarantine,
                            task_id=task_id,
                            use_template_header_row=use_template_header_row
                        )
                        return result
                    except Exception as e:
                        logger.error(f"[CeleryTask] 文件{file_id}同步异常: {e}", exc_info=True)
                        try:
                            await db.rollback()
                        except Exception:
                            pass
                        return {
                            'success': False,
                            'file_id': file_id,
                            'status': 'failed',
                            'message': f'同步异常: {str(e)}'
                        }
                    finally:
                        try:
                            await db.close()
                        except Exception:
                            pass
            
            # 批量处理文件（异步并发）
            tasks = [sync_file_with_semaphore(file_id) for file_id in file_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果（类似 process_batch_sync_background 的逻辑）
            processed_files = 0
            success_files = 0
            failed_files = 0
            skipped_files = 0
            
            for i, result in enumerate(results):
                file_id = file_ids[i]
                
                if isinstance(result, Exception):
                    processed_files += 1
                    failed_files += 1
                    error_msg = f"文件{file_id}同步异常: {str(result)}"
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
                        await progress_tracker.add_error(task_id, f"文件{file_id}: {error_msg}")
                
                # 更新进度
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "status": "processing"
                })
            
            # ⭐ 修复：超时检查（在质量检查前检查）
            def check_timeout():
                """检查任务是否超时"""
                # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致
                task_elapsed = (datetime.now(timezone.utc) - task_start_time).total_seconds()
                return task_elapsed > TASK_TIMEOUT_SECONDS
            
            # ⭐ 修复：数据质量Gate（批量同步完成后自动质量检查）
            # 参考 process_batch_sync_background 的实现
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
                            # ⭐ 修复：在函数内部导入必要的模块（因为函数在run_in_executor中执行，无法访问外层作用域的导入）
                            from backend.models.database import SessionLocal
                            from backend.services.c_class_data_validator import get_c_class_data_validator
                            from datetime import datetime, timezone
                            from modules.core.logger import get_logger
                            
                            logger = get_logger(__name__)
                            db_quality = SessionLocal()
                            try:
                                validator = get_c_class_data_validator(db_quality)
                                quality_scores = []
                                missing_fields_list = []
                                
                                for key, info in platform_shops_dict.items():
                                    try:
                                        # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致
                                        check_result = validator.check_b_class_completeness(
                                            platform_code=info["platform_code"],
                                            shop_id=info["shop_id"],
                                            metric_date=datetime.now(timezone.utc).date()
                                        )
                                        
                                        if check_result and not check_result.get("error"):
                                            quality_scores.append(check_result.get("data_quality_score", 0))
                                            missing_fields = check_result.get("missing_fields", [])  # ⭐ 修复：使用正确的字段名
                                            if missing_fields:
                                                missing_fields_list.extend(missing_fields)
                                    except Exception as check_error:
                                        logger.warning(f"[CeleryTask] 平台{info['platform_code']}质量检查失败: {check_error}")
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
                        
                        # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致
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
            
            # ⭐ 修复：检查是否因超时失败
            # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致
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
            try:
                await db_main.close()
            except Exception:
                pass
    
    # 在同步函数中运行异步代码
    try:
        result = asyncio.run(_async_task())
        return result
    except Exception as exc:
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
```

### Celery 配置更新

```python
# backend/celery_app.py

# ⭐ 修复：更新 include 列表，添加 data_sync_tasks 模块
celery_app = Celery(
    "xihong_erp",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=[
        "backend.tasks.data_processing",
        "backend.tasks.scheduled_tasks",
        "backend.tasks.data_sync_tasks",  # ⭐ 新增：数据同步任务模块
        # ⚠️ v4.6.0 DSS架构重构：已删除mv_refresh（Metabase直接查询原始表，无需物化视图）
        # ⚠️ v4.6.0 DSS架构重构：已删除c_class_calculation（C类数据由Metabase定时计算）
    ]
)

# ⭐ 修复：更新配置，保留现有配置，添加新配置
celery_app.conf.update(
    # ⭐ 保留：时区设置（现有配置）
    timezone='Asia/Shanghai',
    enable_utc=True,
    
    # ⭐ 保留：任务序列化（现有配置）
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_expires=3600,  # 结果过期时间（1小时）
    
    # ⭐ 保留：性能配置（现有配置）
    worker_prefetch_multiplier=4,  # 预取任务数
    worker_max_tasks_per_child=1000,  # 每个worker最多处理1000个任务后重启（防止内存泄漏）
    worker_concurrency=4,  # 并发worker数量
    
    # ⭐ 更新：任务路由（添加 data_sync 队列）
    task_routes={
        'backend.tasks.data_processing.*': {'queue': 'data_processing'},
        'backend.tasks.scheduled_tasks.*': {'queue': 'scheduled'},
        'backend.tasks.data_sync_tasks.*': {'queue': 'data_sync'},  # ⭐ 新增
    },
    
    # ⭐ 新增：任务优先级（需要 Redis >= 5.0 支持）
    task_default_priority=5,  # 默认优先级（1-10，10最高）
    
    # ⭐ 新增：任务持久化
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # Worker 崩溃时重新分配任务
    
    # ⭐ 新增：任务超时
    task_time_limit=1800,  # 30分钟硬超时（强制终止）
    task_soft_time_limit=1500,  # 25分钟软超时（发送 SoftTimeLimitExceeded 异常）
    
    # ⭐ 新增：任务结果清理（可选配置）
    result_backend_transport_options={
        'master_name': 'mymaster',  # Redis Sentinel 配置（可选）
        'visibility_timeout': 3600,  # 结果可见性超时（1小时）
    },
)
```

### API 路由更新

```python
# backend/routers/data_sync.py

from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import uuid
import asyncio

from backend.tasks.data_sync_tasks import sync_single_file_task, sync_batch_task
from backend.models.database import get_async_db
from backend.schemas.data_sync import SingleFileSyncRequest, BatchSyncRequest, BatchSyncByFileIdsRequest
from modules.core.db import CatalogFile
from modules.core.logger import get_logger
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.utils.api_response import success_response, error_response

logger = get_logger(__name__)

# ⭐ 修复：定义 router
router = APIRouter()

@router.post("/data-sync/single")
async def sync_single_file(
    request: SingleFileSyncRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    单文件数据同步（使用 Celery 任务）
    
    ⭐ 修复：添加参数验证和降级处理
    """
    # ⭐ 修复：验证文件是否存在
    result = await db.execute(
        select(CatalogFile).where(CatalogFile.id == request.file_id)
    )
    file_record = result.scalar_one_or_none()
    
    if not file_record:
        return error_response(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"文件{request.file_id}不存在",
            error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
            status_code=404
        )
    
    # 生成 task_id
    task_id = f"single_file_{request.file_id}_{uuid.uuid4().hex[:8]}"
    
    # ⭐ 修复：提交 Celery 任务，添加降级处理
    try:
        celery_task = sync_single_file_task.delay(
            file_id=request.file_id,
            task_id=task_id,
            only_with_template=request.only_with_template,
            allow_quarantine=request.allow_quarantine,
            use_template_header_row=request.use_template_header_row
        )
        
        # 立即返回 task_id
        return success_response(
            data={
                "task_id": task_id,
                "celery_task_id": celery_task.id,  # Celery 任务ID（可选）
                "status": "pending"
            },
            message="同步任务已提交"
        )
    except Exception as e:
        # ⭐ 修复：Celery任务提交失败时的降级处理
        error_type = type(e).__name__
        if "OperationalError" in error_type or "ConnectionError" in error_type:
            # Redis连接失败，降级到 asyncio.create_task()
            logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
            
            # 创建进度任务
            from backend.services.sync_progress_tracker import SyncProgressTracker
            progress_tracker = SyncProgressTracker(db)
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
            
            # 降级到 asyncio.create_task()
            # ⭐ 修复：使用延迟导入避免循环导入
            import importlib
            data_sync_module = importlib.import_module('backend.routers.data_sync')
            asyncio.create_task(
                data_sync_module.process_single_sync_background(
                    file_id=request.file_id,
                    task_id=task_id,
                    only_with_template=request.only_with_template,
                    allow_quarantine=request.allow_quarantine,
                    use_template_header_row=request.use_template_header_row
                )
            )
            
            return success_response(
                data={
                    "task_id": task_id,
                    "status": "pending",
                    "fallback": True,  # 标记为降级模式
                    "message": "Celery不可用，使用降级模式"
                },
                message="同步任务已提交（降级模式）"
            )
        else:
            # 其他错误，返回错误响应
            logger.error(f"[API] Celery任务提交失败: {e}", exc_info=True)
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="同步任务提交失败",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                detail=str(e),
                status_code=500
            )

@router.post("/data-sync/batch")
async def sync_batch(
    request: BatchSyncRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量数据同步（使用 Celery 任务）
    
    ⭐ 修复：添加参数验证和降级处理
    """
    try:
        from backend.services.sync_progress_tracker import SyncProgressTracker
        # ⭐ 修复：使用延迟导入避免循环导入
        import importlib
        data_sync_module = importlib.import_module('backend.routers.data_sync')
        
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_{uuid.uuid4().hex[:8]}"
        
        # 查询待处理文件
        query = select(CatalogFile).where(CatalogFile.status == "pending")
        
        # 平台筛选
        if request.platform and request.platform != "*":
            query = query.where(CatalogFile.platform_code == request.platform)
        
        # 数据域筛选
        if request.domains:
            query = query.where(CatalogFile.data_domain.in_(request.domains))
        
        # ⭐ 修复：粒度筛选
        if request.granularities:
            query = query.where(CatalogFile.granularity.in_(request.granularities))
        
        # ⭐ 修复：时间筛选
        if request.since_hours:
            # ⭐ 修复：使用 UTC 时间，与数据库时间保持一致（统一使用 datetime.now(timezone.utc)）
            from datetime import timezone
            since_time = datetime.now(timezone.utc) - timedelta(hours=request.since_hours)
            query = query.where(CatalogFile.first_seen_at >= since_time)
        
        # 限制数量
        query = query.limit(request.limit)
        
        # 执行查询
        result = await db.execute(query)
        files = result.scalars().all()
        file_ids = [f.id for f in files]
        total_files = len(file_ids)
        
        if total_files == 0:
            return success_response(
                data={
                    "task_id": task_id,
                    "total_files": 0,
                    "processed_files": 0,
                },
                message="没有待处理的文件"
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            task_type="bulk_ingest",
            total_files=total_files
        )
        
        # ⭐ 修复：提交 Celery 任务，添加降级处理
        try:
            celery_task = sync_batch_task.delay(
                file_ids=file_ids,
                task_id=task_id,
                only_with_template=request.only_with_template,
                allow_quarantine=request.allow_quarantine,
                use_template_header_row=True,  # ⭐ 修复：BatchSyncRequest没有此字段，使用固定值True
                max_concurrent=10
            )
            
            # 立即返回 task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,  # Celery 任务ID（可选）
                    "total_files": total_files,
                    "processed_files": 0,
                    "status": "pending"
                },
                message=f"批量同步任务已提交，正在处理{total_files}个文件"
            )
        except Exception as e:
            # ⭐ 修复：Celery任务提交失败时的降级处理
            error_type = type(e).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type:
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # 降级到 asyncio.create_task()
                # ⭐ 修复：使用延迟导入避免循环导入（已在函数开头导入 data_sync_module）
                asyncio.create_task(
                    data_sync_module.process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=request.only_with_template,
                        allow_quarantine=request.allow_quarantine,
                        use_template_header_row=True,  # ⭐ 修复：BatchSyncRequest没有此字段，使用固定值True
                        max_concurrent=10
                    )
                )
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "status": "pending",
                        "fallback": True,  # 标记为降级模式
                        "message": "Celery不可用，使用降级模式"
                    },
                    message="批量同步任务已提交（降级模式）"
                )
            else:
                # 其他错误，返回错误响应
                logger.error(f"[API] Celery任务提交失败: {e}", exc_info=True)
                return error_response(
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="批量同步任务提交失败",
                    error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                    detail=str(e),
                    status_code=500
                )
    except Exception as e:
        # ⭐ 修复：添加完整的错误处理
        logger.error(f"[API] 批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

@router.post("/data-sync/batch-by-ids")
async def sync_batch_by_file_ids(
    request: BatchSyncByFileIdsRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量数据同步（基于文件ID列表，使用 Celery 任务）
    
    ⭐ 修复：添加参数验证和降级处理
    """
    try:
        from backend.services.sync_progress_tracker import SyncProgressTracker
        # ⭐ 修复：使用延迟导入避免循环导入
        import importlib
        data_sync_module = importlib.import_module('backend.routers.data_sync')
        
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_ids_{uuid.uuid4().hex[:8]}"
        
        # ⭐ 修复：验证文件ID列表
        if not request.file_ids or len(request.file_ids) == 0:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件ID列表不能为空",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail="file_ids参数必填且不能为空",
                status_code=400
            )
        
        # 限制文件数量
        if len(request.file_ids) > 1000:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=f"最多支持1000个文件，当前{len(request.file_ids)}个",
                status_code=400
            )
        
        # ⭐ 修复：验证文件是否存在
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id.in_(request.file_ids))
        )
        existing_files = result.scalars().all()
        
        existing_file_ids = [f.id for f in existing_files]
        missing_file_ids = set(request.file_ids) - set(existing_file_ids)
        
        if missing_file_ids:
            logger.warning(f"[API] 部分文件不存在: {missing_file_ids}")
            # 只处理存在的文件
            file_ids = existing_file_ids
        else:
            file_ids = request.file_ids
        
        total_files = len(file_ids)
        
        if total_files == 0:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="没有找到有效的文件",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"请求的文件ID都不存在: {request.file_ids}",
                status_code=404
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            task_type="batch_ingest",
            total_files=total_files
        )
        
        # ⭐ 修复：提交 Celery 任务，添加降级处理
        try:
            celery_task = sync_batch_task.delay(
                file_ids=file_ids,
                task_id=task_id,
                only_with_template=request.only_with_template,
                allow_quarantine=request.allow_quarantine,
                use_template_header_row=request.use_template_header_row,  # ⭐ BatchSyncByFileIdsRequest有此字段
                max_concurrent=10
            )
            
            # 立即返回 task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,  # Celery 任务ID（可选）
                    "total_files": total_files,
                    "processed_files": 0,
                    "status": "pending",
                    "missing_file_ids": list(missing_file_ids) if missing_file_ids else None
                },
                message=f"批量同步任务已提交，正在处理{total_files}个文件"
            )
        except Exception as e:
            # ⭐ 修复：Celery任务提交失败时的降级处理
            error_type = type(e).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type:
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # 降级到 asyncio.create_task()
                # ⭐ 修复：使用延迟导入避免循环导入（已在函数开头导入 data_sync_module）
                asyncio.create_task(
                    data_sync_module.process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=request.only_with_template,
                        allow_quarantine=request.allow_quarantine,
                        use_template_header_row=request.use_template_header_row,  # ⭐ BatchSyncByFileIdsRequest有此字段
                        max_concurrent=10
                    )
                )
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "status": "pending",
                        "fallback": True,  # 标记为降级模式
                        "missing_file_ids": list(missing_file_ids) if missing_file_ids else None,
                        "message": "Celery不可用，使用降级模式"
                    },
                    message="批量同步任务已提交（降级模式）"
                )
            else:
                # 其他错误，返回错误响应
                logger.error(f"[API] Celery任务提交失败: {e}", exc_info=True)
                return error_response(
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="批量同步任务提交失败",
                    error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                    detail=str(e),
                    status_code=500
                )
    except Exception as e:
        # ⭐ 修复：添加完整的错误处理
        logger.error(f"[API] 批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )
```

**注意**：需要更新导入语句，添加 `BatchSyncByFileIdsRequest`：

```python
from backend.schemas.data_sync import SingleFileSyncRequest, BatchSyncRequest, BatchSyncByFileIdsRequest
```

### 任务恢复机制

**服务重启后自动恢复**：

1. **Celery 任务恢复机制**：
   - 配置 `task_acks_late=True`：任务完成后才确认，worker 崩溃时任务不会丢失
   - 配置 `task_reject_on_worker_lost=True`：worker 崩溃时重新分配任务到其他 worker
   - Redis 持久化：确保任务队列不丢失（需要配置 Redis RDB 或 AOF 持久化）
   - Celery worker 启动时，会从 Redis 中恢复未确认的任务（状态为 `PENDING` 或 `STARTED`）
   - 如果任务状态为 `SUCCESS` 或 `FAILURE`，不会重新执行

2. **Redis 持久化配置**（必需）：
   ```bash
   # Redis 配置文件 (redis.conf)
   # 方式1：RDB 持久化（推荐，性能好）
   save 900 1      # 900秒内至少1个key变化时保存
   save 300 10     # 300秒内至少10个key变化时保存
   save 60 10000   # 60秒内至少10000个key变化时保存
   
   # 方式2：AOF 持久化（更可靠，但性能稍差）
   appendonly yes
   appendfsync everysec
   ```

3. **进度恢复**：
   - 使用 `SyncProgressTask` 表存储进度（数据库持久化）
   - 任务恢复后，可以从数据库查询进度
   - 前端可以继续轮询进度
   - 如果任务恢复执行，进度会继续更新

4. **验证步骤**：
   - 启动 Celery worker，提交一个任务
   - 在任务执行过程中，强制停止 worker（模拟崩溃）
   - 重新启动 worker，验证任务是否自动恢复执行
   - 检查 Redis 持久化配置是否生效

### 用户隔离机制

**⚠️ 注意**：当前数据同步 API 没有用户认证机制，用户隔离功能需要先实现用户认证。

**实现方式（Phase 4，待实现）**：
1. **前提条件**：在 API 路由中添加用户认证（`get_current_user` 依赖）
2. 在任务参数中添加 `user_id`（从认证信息中获取）
3. 在任务提交前检查用户的任务数量（查询 Redis 或数据库）
4. 如果超过限制，返回错误或将任务放入队列等待

**配置**：
```python
# backend/utils/config.py

MAX_TASKS_PER_USER = int(os.getenv("MAX_TASKS_PER_USER", "5"))  # 每个用户最多5个并发任务
```

**临时方案**（Phase 1-3）：
- 暂时不实现用户隔离功能
- 使用全局任务数量限制（所有用户共享）
- 在 Phase 4 中实现用户认证和隔离

## 风险

### 风险 1：Celery Worker 崩溃

**影响**：任务执行中断，需要重新执行

**缓解措施**：
1. 使用 supervisor/systemd 自动重启 worker
2. 配置 `task_acks_late=True`，任务完成后才确认
3. 配置 `task_reject_on_worker_lost=True`，worker 崩溃时重新分配任务

### 风险 2：Redis 连接失败

**影响**：无法提交任务，无法查询任务状态

**缓解措施**：
1. ⭐ **修复**：实现降级处理机制（Celery任务提交失败时，降级到 `asyncio.create_task()`）
2. 实现连接重试机制
3. 添加健康检查端点
4. 使用 Redis Sentinel 实现高可用
5. ⭐ **修复**：在API路由中添加 `try-except` 捕获 `OperationalError` 和 `ConnectionError`，自动降级

### 风险 3：任务序列化失败

**影响**：无法提交任务

**缓解措施**：
1. 使用 JSON 序列化，避免复杂对象
2. 任务参数只包含简单类型（int, str, bool, list, dict）
3. 添加参数验证

### 风险 4：任务重复执行

**影响**：数据重复导入

**缓解措施**：
1. 使用任务 ID 去重（在 `SyncProgressTask` 表中，`task_id` 是主键）
2. 在 `DataSyncService` 中检查文件状态（如果文件已处理，跳过或更新）
3. 使用数据库唯一约束防止重复（去重策略：INSERT 或 UPSERT）
4. 配置 `task_acks_late=True`，确保任务完成后才确认，避免重复执行

### 风险 5：Redis 版本不支持任务优先级

**影响**：任务优先级功能无法使用

**缓解措施**：
1. 验证 Redis 版本（需要 >= 5.0）
2. 如果不支持，暂时禁用优先级功能，使用队列分离代替
3. 升级 Redis 到支持优先级的版本

### 风险 6：asyncio.run() 在已有事件循环中失败

**影响**：任务执行失败

**缓解措施**：
1. 使用 `asyncio.run()` 包装整个异步逻辑（创建新的事件循环）
2. 如果 Celery worker 已经运行事件循环，使用 `nest_asyncio` 库（可选）
3. 测试验证：确保在 Celery worker 中正确执行

## 迁移计划

### 阶段 1：准备（1-2 天）
1. 验证 Redis 连接
2. 更新 Celery 配置
3. 创建任务模块框架

### 阶段 2：实现（3-5 天）
1. 实现单文件同步任务
2. 实现批量同步任务
3. 更新 API 路由
4. 添加任务恢复机制

### 阶段 3：测试（2-3 天）
1. 单元测试
2. 集成测试
3. 性能测试
4. 压力测试

### 阶段 4：部署（1 天）
1. 部署 Celery Worker
2. 验证任务执行
3. 监控任务状态

## 开放问题

1. **任务优先级策略**：如何确定任务的优先级？（用户级别、任务类型、文件大小？）
   - **建议**：Phase 4 实现，优先级策略：
     - 高优先级（priority=8-10）：紧急任务、管理员任务
     - 中优先级（priority=5-7）：普通用户任务（默认）
     - 低优先级（priority=1-4）：批量任务、定时任务

2. **Worker 数量**：生产环境应该启动多少个 worker？（根据 CPU 核心数和负载）
   - **建议**：根据 CPU 核心数和负载情况
     - 开发环境：1-2 个 worker
     - 生产环境：CPU 核心数 / 2（每个 worker 4 个并发任务）
     - 例如：16 核服务器，建议 4-8 个 worker

3. **任务超时**：任务执行多长时间应该超时？（当前是 30 分钟）
   - **已解决**：在任务定义和 Celery 配置中都设置为 30 分钟
   - `time_limit=1800`（硬超时）
   - `soft_time_limit=1500`（软超时）

4. **任务清理**：多久清理一次已完成的任务？（Redis 中的任务结果）
   - **已解决**：`result_expires=3600`（1 小时）
   - 任务结果会在 1 小时后自动过期
   - 可以考虑添加定期清理任务（清理超过 7 天的任务结果）

## 实施注意事项

1. **保持向后兼容**：迁移期间，保留 `asyncio.create_task()` 代码作为备份
2. **渐进式迁移**：先迁移单文件同步，验证稳定后再迁移批量同步
3. **监控和日志**：添加详细的任务执行日志和监控指标
4. **文档更新**：更新部署文档和运维文档
5. ⭐ **修复**：Windows平台部署注意事项
   - Windows平台必须使用 `--pool=solo`（Celery在Windows上不支持prefork）
   - 启动命令：`celery -A backend.celery_app worker --loglevel=info --queues=data_sync --pool=solo --concurrency=4`
   - Linux/Mac平台：`celery -A backend.celery_app worker --loglevel=info --queues=data_sync --concurrency=4`
   - ⭐ **修复**：并发配置方式
     - 方式1：在 `backend/celery_app.py` 中设置 `celery_app.conf.worker_concurrency=4`
     - 方式2：启动命令中使用 `--concurrency=4` 参数（优先级更高，推荐）
     - 推荐使用命令行参数，便于不同环境使用不同配置
6. ⭐ **修复**：实现降级处理机制
   - Celery任务提交失败时（Redis连接失败），自动降级到 `asyncio.create_task()`
   - 确保系统在Redis不可用时仍能正常工作（降级模式）

