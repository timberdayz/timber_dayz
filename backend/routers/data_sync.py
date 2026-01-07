#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步API路由（Data Sync API）

v4.12.0新增：
- 统一的数据同步API入口
- 使用DataSyncService（直接函数调用，不通过HTTP）
- 使用SyncProgressTracker（数据库存储，持久化）

职责：
- 只负责API接口（参数解析、响应格式化）
- 业务逻辑由DataSyncService处理

v4.18.0: Pydantic模型已迁移到backend/schemas/data_sync.py（Contract-First架构）
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Request, Body, Path
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path as PathLib  # ⭐ 修复：重命名避免与 fastapi.Path 冲突
import uuid
import asyncio
import pandas as pd

from backend.models.database import get_db, get_async_db, SessionLocal, AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.data_sync_service import DataSyncService
from backend.services.sync_progress_tracker import SyncProgressTracker
from backend.routers.auth import get_current_user  # ⭐ Phase 4.2: 用户认证
from backend.services.user_task_quota import get_user_task_quota_service  # ⭐ Phase 4.2: 用户任务配额

# ⭐ Phase 2: API 限流（使用 slowapi）
# ⭐ v4.19.4 更新：使用基于角色的动态限流
try:
    from backend.middleware.rate_limiter import limiter, role_based_rate_limit
    RATE_LIMIT_ENABLED = True
except ImportError:
    limiter = None
    role_based_rate_limit = None
    RATE_LIMIT_ENABLED = False

# ⭐ v4.19.4 保留：条件装饰器辅助函数（向后兼容，但建议使用 role_based_rate_limit）
def conditional_rate_limit(limit_str: str):
    """条件应用限流装饰器（已废弃，建议使用 role_based_rate_limit）"""
    if RATE_LIMIT_ENABLED and limiter:
        return limiter.limit(limit_str)
    else:
        # 返回一个无操作的装饰器
        def noop_decorator(func):
            return func
        return noop_decorator

# ⭐ v4.18.2修复：全局并发控制，限制同时运行的后台同步任务数量
# 最多允许10个并发任务，避免资源耗尽
MAX_CONCURRENT_SYNC_TASKS = asyncio.Semaphore(10)
from backend.services.c_class_data_validator import get_c_class_data_validator
from backend.services.data_loss_analyzer import (
    analyze_data_loss, check_data_loss_threshold,
    async_analyze_data_loss, async_check_data_loss_threshold  # ⭐ v4.18.2新增：异步版本
)
from backend.services.field_mapping_validator import validate_field_mapping, calculate_mapping_quality_score
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile
from modules.core.logger import get_logger
from sqlalchemy import select, func, and_, distinct

# v4.18.0: 导入schemas（Contract-First架构）
from backend.schemas.data_sync import (
    SingleFileSyncRequest,
    BatchSyncRequest,
    BatchSyncByFileIdsRequest,
    DataSyncFilePreviewRequest,
    FileListRequest,
    CeleryTaskStatusResponse,  # ⭐ Phase 1.4.3: 任务状态管理
    CancelTaskResponse,  # ⭐ Phase 1.4.3: 任务状态管理
    RetryTaskResponse,  # ⭐ Phase 1.4.3: 任务状态管理
)

logger = get_logger(__name__)
router = APIRouter()


# ==================== 数据同步API ====================

@router.post("/data-sync/preview")
async def preview_file(
    request: DataSyncFilePreviewRequest,
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    文件预览API（支持表头行参数）⭐ **新增（2025-01-31）**
    
    功能：
    - 使用用户手动选择的表头行读取文件
    - 不进行自动检测，直接使用用户选择的表头行
    - 返回数据预览（前100行）、原始表头字段列表、示例数据
    
    Args:
        file_id: 文件ID
        header_row: 表头行（0-based，0=Excel第1行，1=Excel第2行...）
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        from backend.services.excel_parser import ExcelParser
        
        # 1. 获取文件信息（⭐ v4.18.2：使用 await）
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == request.file_id)
        )
        catalog_record = result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件未注册",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件未注册: id={request.file_id}",
                recovery_suggestion="请先扫描采集文件，确保文件已注册到系统中",
                status_code=404
            )
        
        file_path_relative = catalog_record.file_path
        
        # ⭐ v4.19.8修复：使用 to_absolute_path 正确解析路径（支持Docker容器和Windows环境）
        from modules.core.path_manager import to_absolute_path
        file_path = to_absolute_path(file_path_relative)
        
        # ⭐ v4.18.2修复：使用 run_in_executor 包装文件系统检查，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        file_exists = await loop.run_in_executor(
            None,
            lambda: file_path.exists()
        )
        if not file_exists:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_path}（原始路径: {file_path_relative}）",
                recovery_suggestion="请检查文件路径是否正确，或重新扫描采集文件",
                status_code=404
            )
        
        # 2. 使用用户选择的表头行读取文件（不自动检测）
        logger.info(f"[DataSync Preview] 使用表头行 {request.header_row} 读取文件: {catalog_record.file_name}")
        
        # ⭐ v4.18.2修复：使用 run_in_executor 包装文件大小获取，避免阻塞事件循环
        file_size_mb = await loop.run_in_executor(
            None,
            lambda: PathLib(file_path).stat().st_size / (1024 * 1024)
        )
        preview_rows = 50 if file_size_mb > 10 else 100
        
        # ⭐ v4.18.2修复：使用 run_in_executor 包装文件读取，避免阻塞事件循环
        df = await loop.run_in_executor(
            None,
            ExcelParser.read_excel,
            file_path,
            request.header_row,  # ⭐ 直接使用用户选择的表头行
            preview_rows
        )
        
        # 3. 规范化处理（合并单元格还原）
        normalization_report = {}
        try:
            df, normalization_report = ExcelParser.normalize_table(
                df,
                data_domain=catalog_record.data_domain or "products",
                file_size_mb=file_size_mb
            )
        except Exception as norm_error:
            logger.warning(f"[DataSync Preview] 规范化失败: {norm_error}", exc_info=True)
            normalization_report = {"error": str(norm_error)}
        
        # 4. 数据清洗
        df.columns = [str(col).strip() for col in df.columns]
        df = df.dropna(how='all')
        df = df.fillna('')
        
        # 5. 提取原始表头字段列表和示例数据
        header_columns = df.columns.tolist()
        sample_data = {}
        if len(df) > 0:
            first_row = df.iloc[0]
            for col in header_columns:
                sample_data[col] = str(first_row[col]) if pd.notna(first_row[col]) else ""
        
        # 6. 转换为前端格式
        preview_data = df.head(100).to_dict('records')
        
        return success_response(
            data={
                "preview_data": preview_data,
                "header_columns": header_columns,
                "sample_data": sample_data,
                "row_count": len(df),
                "column_count": len(header_columns),
                "file_name": catalog_record.file_name,
                "file_size": file_size_mb,
                "header_row": request.header_row,
                "normalization_report": normalization_report
            },
            message=f"文件预览成功（表头行: {request.header_row}）"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Preview] 预览失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="文件预览失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e)[:500],
            recovery_suggestion="建议：1) 检查文件格式是否正确；2) 尝试调整表头行；3) 联系技术支持",
            status_code=500
        )


@router.get("/data-sync/files")
async def list_files(
    platform: Optional[str] = Query(None, description="平台代码"),
    domain: Optional[str] = Query(None, description="数据域"),
    granularity: Optional[str] = Query(None, description="粒度"),
    sub_domain: Optional[str] = Query(None, description="子类型"),
    status: Optional[str] = Query(None, description="状态（pending/ingested/failed/partial_success/quarantined/needs_shop，为空则显示所有状态）"),  # ⭐ v4.17.3修复：默认None，显示所有状态
    page: int = Query(1, description="页码", ge=1),  # v4.18.0新增：分页支持
    page_size: int = Query(50, description="每页数量", ge=1, le=200),  # v4.18.0新增：分页支持
    limit: int = Query(None, description="数量限制（已废弃，使用page和page_size）"),  # v4.18.0：向后兼容
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    文件列表API ⭐ **新增（2025-01-31）**
    
    功能：
    - 显示待同步文件列表
    - 支持筛选：platform, domain, granularity, sub_domain, status
    - 返回文件列表和模板匹配状态
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        from backend.services.template_matcher import get_template_matcher
        
        # 1. 构建查询条件
        query = select(CatalogFile)
        conditions = []
        
        if platform:
            conditions.append(CatalogFile.platform_code == platform)
        if domain:
            conditions.append(CatalogFile.data_domain == domain)
        if granularity:
            conditions.append(CatalogFile.granularity == granularity)
        if sub_domain:
            conditions.append(CatalogFile.sub_domain == sub_domain)
        if status:
            conditions.append(CatalogFile.status == status)
        
        if conditions:
            query = query.where(*conditions)
        
        # v4.18.0: 计算总数（用于分页）
        # ⭐ v4.18.2：使用 await 进行异步查询
        count_query = select(func.count(CatalogFile.id))
        if conditions:
            count_query = count_query.where(*conditions)
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0
        
        # v4.18.0: 分页逻辑（兼容旧的limit参数）
        if limit is not None:
            # 兼容旧版本：如果提供了limit，使用limit
            query = query.order_by(CatalogFile.first_seen_at.desc()).limit(limit)
        else:
            # 新版本：使用page和page_size
            offset = (page - 1) * page_size
            query = query.order_by(CatalogFile.first_seen_at.desc()).offset(offset).limit(page_size)
        
        # 2. 查询文件列表（⭐ v4.18.2：使用 await）
        result = await db.execute(query)
        files = result.scalars().all()
        
        # ⭐ v4.19.5 优化：预加载所有已发布模板，减少重复查询
        from modules.core.db import FieldMappingTemplate
        from sqlalchemy import desc
        
        # 预加载所有已发布模板（一次性查询）
        templates_result = await db.execute(
            select(FieldMappingTemplate).where(
                FieldMappingTemplate.status == 'published'
            ).order_by(desc(FieldMappingTemplate.version))
        )
        all_templates = templates_result.scalars().all()
        
        # 构建模板索引（按 platform/data_domain/granularity/sub_domain）
        # 使用字典存储，key 为匹配键，value 为模板对象
        template_cache = {}
        for t in all_templates:
            # Level 1 精确匹配键
            key1 = f"{t.platform}:{t.data_domain}:{t.granularity or ''}:{t.sub_domain or ''}"
            if key1 not in template_cache:
                template_cache[key1] = t
            # Level 2 宽松匹配键（忽略 sub_domain）
            key2 = f"{t.platform}:{t.data_domain}:{t.granularity or ''}:"
            if key2 not in template_cache:
                template_cache[key2] = t
        
        # 3. 检查模板匹配状态
        template_matcher = get_template_matcher(db)
        file_list = []
        
        # ⭐ v4.18.2修复：在循环外获取事件循环，避免重复获取
        loop = asyncio.get_running_loop()
        
        for file_record in files:
            # ⭐ v4.19.5 优化：使用缓存快速匹配模板，避免重复查询数据库
            template = None
            platform = file_record.platform_code or ""
            data_domain = file_record.data_domain or ""
            granularity = file_record.granularity or ""
            sub_domain = file_record.sub_domain or ""
            
            # Level 1: 精确匹配（包含 sub_domain）
            key1 = f"{platform}:{data_domain}:{granularity}:{sub_domain}"
            if key1 in template_cache:
                template = template_cache[key1]
            else:
                # Level 2: 宽松匹配（忽略 sub_domain）
                key2 = f"{platform}:{data_domain}:{granularity}:"
                if key2 in template_cache:
                    template = template_cache[key2]
                else:
                    # 降级：使用模板匹配器（如果缓存未命中）
                    template = await template_matcher.find_best_template(
                        platform=platform,
                        data_domain=data_domain,
                        granularity=granularity,
                        sub_domain=sub_domain if sub_domain else None
                    )
            
            # ⭐ 修复：使用安全路径解析，确保文件大小正确显示
            from modules.core.path_manager import get_project_root, get_data_input_dir, get_data_raw_dir
            
            # 解析文件路径（支持相对路径和绝对路径）
            file_path_str = file_record.file_path
            if PathLib(file_path_str).is_absolute():
                resolved_path = PathLib(file_path_str)
            else:
                # 相对路径：从项目根目录解析
                project_root = get_project_root()
                resolved_path = project_root / file_path_str
            
            # ⭐ v4.18.2修复：使用 run_in_executor 包装文件系统操作，避免阻塞事件循环
            # 获取文件大小（如果文件存在）
            file_size = 0
            file_exists = await loop.run_in_executor(
                None,
                lambda: resolved_path.exists()
            )
            if file_exists:
                try:
                    file_size = await loop.run_in_executor(
                        None,
                        lambda: resolved_path.stat().st_size
                    )
                except Exception as e:
                    logger.warning(f"[DataSync Files] 获取文件大小失败: {file_path_str}, 错误: {e}")
            
            file_list.append({
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": file_record.platform_code,
                "domain": file_record.data_domain,
                "granularity": file_record.granularity,
                "sub_domain": file_record.sub_domain,
                "file_size": file_size,
                "file_path": str(resolved_path),  # ⭐ 新增：返回解析后的文件路径（用于调试）
                "collected_at": file_record.first_seen_at.isoformat() if file_record.first_seen_at else None,
                "has_template": template is not None,
                "template_name": template.template_name if template else None,
                "template_header_row": template.header_row if template and hasattr(template, 'header_row') else None,  # ⭐ 新增：模板表头行
                "status": file_record.status
            })
        
        return success_response(
            data={
                "files": file_list,
                "total": total_count,  # v4.18.0: 返回总数（用于分页）
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1
            },
            message=f"查询到 {len(file_list)} 个文件（共 {total_count} 个）"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Files] 查询文件列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接，或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/single")
@role_based_rate_limit(endpoint_type="data_sync")  # ⭐ v4.19.4: 基于角色的动态限流
async def sync_single_file(
    body: SingleFileSyncRequest,  # ⭐ 修复：重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # ⭐ 修复：参数名必须为 request（slowapi 要求）
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    单文件数据同步（使用 Celery 任务）
    
    ⭐ Phase 2: 限流（10次/分钟）
    """
    """
    单文件数据同步（使用 Celery 任务）
    
    v4.19.1 恢复：使用 Celery 任务队列执行数据同步
    - 任务持久化：任务存储在 Redis 中，服务器重启后自动恢复
    - 资源隔离：任务在独立的 Celery worker 进程中执行，不影响 API 服务
    - 降级处理：Celery 不可用时，降级到 asyncio.create_task()
    """
    try:
        # 验证文件是否存在
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == body.file_id)
        )
        catalog_file = result.scalar_one_or_none()
        if not catalog_file:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                detail=f"文件ID: {body.file_id}",
                recovery_suggestion="请检查文件ID是否正确",
                status_code=404
            )
        
        # 检查状态（防止并发）
        if catalog_file.status == 'processing':
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="文件正在处理中",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail=f"文件ID: {body.file_id}, 文件名: {catalog_file.file_name}",
                recovery_suggestion="请等待当前同步任务完成",
                status_code=409
            )
        
        # ⭐ Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务（最多允许 {quota_service.max_concurrent_tasks} 个并发任务）",
                status_code=429  # Too Many Requests
            )
        
        # 生成task_id
        task_id = f"single_file_{body.file_id}_{uuid.uuid4().hex[:8]}"
        
        # v4.19.1: 提交 Celery 任务，添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_single_file_task
            
            # ⭐ 修复：在提交Celery任务之前，先创建进度记录（避免前端查询404）
            # 注意：create_task默认状态就是pending（数据库约束允许的状态）
            progress_tracker = SyncProgressTracker(db)
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
            # 可选：更新消息说明任务已提交
            await progress_tracker.update_task(task_id, {
                "message": "任务已提交，等待Celery worker处理"
            })
            
            # ⭐ Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # ⭐ Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_single_file_task.apply_async(
                args=(body.file_id, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': body.use_template_header_row,
                    'user_id': user_id  # ⭐ Phase 4.2: 添加用户ID（用于审计和配额管理）
                },
                priority=body.priority  # ⭐ Phase 4: 任务优先级（1-10，10最高）
            )
            
            logger.info(
                f"[API] 单文件同步任务已提交 file_id={body.file_id}, task_id={task_id}, "
                f"celery_task_id={celery_task.id}"
            )
            
            # 立即返回task_id
            return success_response(
                data={
                    'task_id': task_id,
                    'celery_task_id': celery_task.id,
                    'file_id': body.file_id,
                    'file_name': catalog_file.file_name,
                    'status': 'pending',  # ⭐ 修复：使用pending状态（与数据库一致）
                    'message': '同步任务已提交，正在后台处理'
                },
                message='同步任务已提交'
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # 创建进度任务
                progress_tracker = SyncProgressTracker(db)
                await progress_tracker.create_task(
                    task_id=task_id,
                    task_type="single_file",
                    total_files=1
                )
                
                # ⭐ Phase 4.2: 增加用户任务计数（降级模式也需要配额管理）
                await quota_service.increment_user_task_count(user_id)
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_single_sync_background(
                        file_id=body.file_id,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=body.use_template_header_row,
                        user_id=user_id  # ⭐ Phase 4.2: 传递用户ID
                    )
                )
                
                logger.info(
                    f"[API] 单文件同步任务已提交（降级模式）file_id={body.file_id}, task_id={task_id}"
                )
                
                return success_response(
                    data={
                        'task_id': task_id,
                        'file_id': body.file_id,
                        'file_name': catalog_file.file_name,
                        'status': 'pending',  # ⭐ 修复：使用pending状态（与数据库一致）
                        'fallback': True,
                        'message': 'Celery不可用，使用降级模式'
                    },
                    message='同步任务已提交（降级模式）'
                )
            else:
                # 其他错误，重新抛出
                raise celery_error
        
    except Exception as e:
        logger.error(f"[API] 单文件同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="单文件同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


# ==================== 后台任务处理函数 ====================

async def process_single_sync_background(
    file_id: int,
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,
    user_id: int = None  # ⭐ Phase 4.2: 用户ID（可选，用于配额管理）
):
    """
    后台单文件同步处理函数（使用 asyncio.create_task）
    
    v4.18.0新增：将单文件同步改为异步处理，避免前端页面阻塞
    v4.18.2更新：使用AsyncSessionLocal真异步会话，避免阻塞事件循环
    v4.18.2修复：使用 asyncio.create_task() 替代 BackgroundTasks，添加并发控制
    - 立即返回task_id
    - 后台异步处理
    - 进度跟踪（数据库存储）
    - 并发控制（Semaphore）
    """
    # ⭐ v4.18.2修复：使用 Semaphore 控制并发
    # ⭐ v4.18.2性能监控：记录任务开始时间
    import time
    task_start_time = time.time()
    async with MAX_CONCURRENT_SYNC_TASKS:
        # ⭐ v4.18.2修复：使用异步会话
        db = AsyncSessionLocal()
        progress_tracker = SyncProgressTracker(db)
    
        try:
            logger.info(f"[BackgroundTask] 开始单文件同步 file_id={file_id}, task_id={task_id}")
            
            # 创建进度任务（异步方法）
            await progress_tracker.create_task(
                task_id=task_id,
                task_type="single_file",
                total_files=1
            )
            await progress_tracker.update_task(task_id, {"status": "processing"})
            
            # 创建独立的异步数据库会话进行同步
            db_sync = AsyncSessionLocal()
            try:
                sync_service = DataSyncService(db_sync)
                result = await sync_service.sync_single_file(
                    file_id=file_id,
                    only_with_template=only_with_template,
                    allow_quarantine=allow_quarantine,
                    task_id=task_id,
                    use_template_header_row=use_template_header_row
                )
                
                # 更新进度并完成任务（异步方法）
                if result.get('success', False):
                    await progress_tracker.update_task(task_id, {
                        "processed_files": 1,
                        "current_file": result.get('file_name', ''),
                        "file_progress": 100.0
                    })
                    await progress_tracker.complete_task(task_id, success=True)
                    # ⭐ v4.18.2性能监控：记录任务总耗时
                    task_elapsed = (time.time() - task_start_time) * 1000
                    logger.info(
                        f"[BackgroundTask] 单文件同步成功 file_id={file_id}, task_id={task_id}, "
                        f"总耗时={task_elapsed:.2f}ms"
                    )
                else:
                    # 记录错误
                    error_msg = result.get('message', '同步失败')
                    await progress_tracker.update_task(task_id, {
                        "processed_files": 1,
                        "current_file": result.get('file_name', ''),
                        "file_progress": 100.0
                    })
                    await progress_tracker.add_error(task_id, error_msg)
                    await progress_tracker.complete_task(task_id, success=False, error=error_msg)
                    # ⭐ v4.18.2性能监控：记录任务总耗时
                    task_elapsed = (time.time() - task_start_time) * 1000
                    logger.warning(
                        f"[BackgroundTask] 单文件同步失败 file_id={file_id}, task_id={task_id}, "
                        f"message={error_msg}, 总耗时={task_elapsed:.2f}ms"
                    )
            finally:
                await db_sync.close()
                
        except Exception as e:
            logger.error(f"[BackgroundTask] 单文件同步异常 file_id={file_id}, task_id={task_id}: {e}", exc_info=True)
            try:
                error_msg = str(e)
                await progress_tracker.add_error(task_id, error_msg)
                await progress_tracker.complete_task(task_id, success=False, error=error_msg)
            except Exception:
                pass
        finally:
            # ⭐ Phase 4.2: 减少用户任务计数（任务完成或失败时）
            if user_id:
                try:
                    quota_service = get_user_task_quota_service()
                    await quota_service.decrement_user_task_count(user_id)
                except Exception as quota_error:
                    logger.warning(f"[BackgroundTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
            
            try:
                await db.close()
            except Exception:
                pass


async def process_batch_sync_background(
    file_ids: List[int],
    task_id: str,
    only_with_template: bool = True,
    allow_quarantine: bool = True,
    use_template_header_row: bool = True,  # ⭐ 新增：使用模板表头行
    max_concurrent: int = 10,
    user_id: int = None  # ⭐ Phase 4.2: 用户ID（可选，用于配额管理）
):
    """
    后台批量同步处理函数（使用FastAPI BackgroundTasks）
    
    ⭐ v4.12.2简化：使用FastAPI BackgroundTasks替代Celery
    v4.18.2更新：使用AsyncSessionLocal真异步会话，避免阻塞事件循环
    - 支持并发控制（最多10个并发）
    - 自动数据质量Gate检查
    - 进度跟踪（数据库存储）
    """
    # ⭐ v4.18.2修复：使用异步会话
    db_main = AsyncSessionLocal()
    progress_tracker = SyncProgressTracker(db_main)
    
    # ⭐ v4.17.1新增：任务超时保护（默认30分钟）
    TASK_TIMEOUT_SECONDS = 30 * 60  # 30分钟
    task_start_time = datetime.now()
    
    try:
        logger.info(f"[BackgroundTask] 开始批量同步 {len(file_ids)} 个文件, task_id={task_id}, 超时时间={TASK_TIMEOUT_SECONDS}秒")
        
        # 统计变量
        processed_files = 0
        success_files = 0
        failed_files = 0
        skipped_files = 0  # ⭐ 新增：跳过文件数（全部数据重复）
        total_rows = 0
        valid_rows = 0
        error_rows = 0
        quarantined_rows = 0
        
        def check_timeout() -> bool:
            """检查任务是否超时"""
            elapsed = (datetime.now() - task_start_time).total_seconds()
            if elapsed > TASK_TIMEOUT_SECONDS:
                logger.warning(
                    f"[BackgroundTask] 任务{task_id}超时: 已运行{elapsed:.1f}秒，超过限制{TASK_TIMEOUT_SECONDS}秒"
                )
                return True
            return False
        
        # ⭐ 并发控制（使用信号量限制并发数）
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def sync_file_with_semaphore(file_id: int) -> Dict[str, Any]:
            """
            带信号量的文件同步
            
            ⭐ 修复：每个协程使用独立的数据库会话，避免并发冲突
            v4.18.2更新：使用异步会话
            """
            async with semaphore:
                # ⭐ v4.18.2修复：为每个协程创建独立的异步数据库会话
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
                    # 记录协程级别的异常
                    logger.error(f"[BackgroundTask] 文件{file_id}同步异常: {e}", exc_info=True)
                    # ⭐ v4.18.2修复：确保异常时回滚事务并关闭会话（异步）
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    # 返回错误结果而不是抛出异常（让gather收集）
                    return {
                        'success': False,
                        'file_id': file_id,
                        'status': 'failed',
                        'message': f'同步异常: {str(e)}'
                    }
                finally:
                    # ⭐ v4.18.2修复：确保每个协程的异步会话都被正确关闭
                    try:
                        await db.close()
                    except Exception:
                        pass
        
        # ⭐ v4.17.1新增：超时检查 - 在开始处理前检查
        if check_timeout():
            raise TimeoutError(f"任务{task_id}在开始处理前已超时")
        
        # 批量处理文件（异步并发）
        tasks = [sync_file_with_semaphore(file_id) for file_id in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # ⭐ v4.17.1新增：超时检查 - 在处理完成后检查
        if check_timeout():
            logger.warning(f"[BackgroundTask] 任务{task_id}在处理完成后发现超时，但已完成处理")
        
        # 处理结果（使用主会话查询文件信息）
        for i, result in enumerate(results):
            # ⭐ v4.17.1新增：在处理每个文件结果时检查超时
            if check_timeout():
                logger.warning(
                    f"[BackgroundTask] 任务{task_id}在处理结果时超时，已处理{processed_files}/{len(file_ids)}个文件，"
                    f"剩余{len(file_ids) - processed_files}个文件未处理"
                )
                # 标记剩余文件为超时失败
                remaining_files = len(file_ids) - processed_files
                failed_files += remaining_files
                processed_files = len(file_ids)  # 标记所有文件已处理
                break  # 停止处理剩余文件
            
            file_id = file_ids[i]
            
            # ⭐ v4.15.0修复：获取文件信息时处理事务错误
            file_name = f"文件{file_id}"
            try:
                # v4.18.2更新：使用异步查询
                result_query = await db_main.execute(
                    select(CatalogFile).where(CatalogFile.id == file_id)
                )
                file_record = result_query.scalar_one_or_none()
                if file_record:
                    file_name = file_record.file_name
            except Exception as query_error:
                # 如果查询失败（可能是事务错误），记录警告但继续处理
                error_str = str(query_error)
                is_transaction_error = (
                    'InFailedSqlTransaction' in error_str or 
                    'current transaction is aborted' in error_str.lower()
                )
                if is_transaction_error:
                    logger.warning(f"[BackgroundTask] 查询文件信息时事务错误，尝试回滚: {query_error}")
                    try:
                        await db_main.rollback()
                        # 重试查询（异步）
                        result_query = await db_main.execute(
                            select(CatalogFile).where(CatalogFile.id == file_id)
                        )
                        file_record = result_query.scalar_one_or_none()
                        if file_record:
                            file_name = file_record.file_name
                    except Exception as retry_error:
                        logger.error(f"[BackgroundTask] 重试查询文件信息失败: {retry_error}")
                else:
                    logger.error(f"[BackgroundTask] 查询文件信息失败: {query_error}")
            
            if isinstance(result, Exception):
                # ⭐ v4.15.0修复：异常情况（这种情况不应该发生，因为我们已经修复了协程异常处理）
                processed_files += 1
                failed_files += 1
                error_str = str(result)
                error_type = type(result).__name__
                
                # 构建详细的错误消息
                if 'InFailedSqlTransaction' in error_str or 'current transaction is aborted' in error_str.lower():
                    error_msg = f"文件{file_name}({file_id})数据库事务错误: {error_str}（可能是并发冲突）"
                else:
                    error_msg = f"文件{file_name}({file_id})同步异常 ({error_type}): {error_str}"
                
                await progress_tracker.add_error(task_id, error_msg)
                logger.error(f"[BackgroundTask] {error_msg}", exc_info=True)
                
                # 更新进度（异步）
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "current_file": file_name,
                    "status": "processing"
                })
            else:
                # 正常结果
                processed_files += 1
                
                # 累计行数统计
                total_rows += result.get("staged", 0) + result.get("imported", 0) + result.get("quarantined", 0)
                valid_rows += result.get("imported", 0)
                quarantined_rows += result.get("quarantined", 0)
                
                if result.get("success"):
                    # ⭐ v4.15.0增强：区分INSERT策略的跳过和UPSERT策略的更新
                    skip_reason = result.get("skip_reason", "")
                    
                    # 检查是否是已入库文件跳过
                    if skip_reason == "file_already_ingested":
                        # 已入库文件：统计为跳过（不是失败）
                        skipped_files += 1
                        logger.info(
                            f"[BackgroundTask] [v4.15.0] 文件{file_name}({file_id})已入库，跳过同步"
                        )
                    else:
                        import_stats = result.get("import_stats")
                        if import_stats and import_stats.get("updated", 0) > 0:
                            # UPSERT策略：有更新的文件统计为成功（更新）
                            success_files += 1
                            logger.info(
                                f"[BackgroundTask] [v4.15.0] 文件{file_name}({file_id})使用UPSERT策略: "
                                f"新插入{import_stats.get('inserted', 0)}行，更新{import_stats.get('updated', 0)}行"
                            )
                        elif result.get("skipped", False):
                            # ⭐ v4.16.0更新：检查是否有更新统计信息（UPSERT策略）
                            import_stats = result.get("import_stats", {})
                            updated_count = import_stats.get('updated', 0) if import_stats else 0
                            
                            if updated_count > 0:
                                # UPSERT策略：有更新，统计为成功（更新）
                                success_files += 1
                                logger.info(
                                    f"[BackgroundTask] [v4.16.0] 文件{file_name}({file_id})使用UPSERT策略: "
                                    f"所有数据都已存在，已更新{updated_count}行"
                                )
                            else:
                                # INSERT策略或异常情况：全部数据重复，统计为跳过
                                skipped_files += 1
                                logger.info(
                                    f"[BackgroundTask] 文件{file_name}({file_id})所有数据都已存在，已跳过重复数据"
                                )
                        else:
                            # 正常插入
                            success_files += 1
                else:
                    failed_files += 1
                    error_rows += result.get("staged", 0)
                    
                    # ⭐ v4.15.0修复：获取详细的错误消息
                    error_message = result.get('message')
                    if not error_message or error_message == '未知错误':
                        # 尝试从其他字段获取错误信息
                        error_message = result.get('error') or result.get('detail') or f"同步失败（状态: {result.get('status', 'unknown')}）"
                    
                    error_msg = f"文件{file_name}({file_id})同步失败: {error_message}"
                    await progress_tracker.add_error(task_id, error_msg)
                    logger.error(f"[BackgroundTask] {error_msg}")
                
                # 更新进度（将跳过文件数存储在task_details中）（异步）
                task_details = {"skipped_files": skipped_files}
                await progress_tracker.update_task(task_id, {
                    "processed_files": processed_files,
                    "total_rows": total_rows,
                    "processed_rows": valid_rows + quarantined_rows + error_rows,
                    "valid_rows": valid_rows,
                    "quarantined_rows": quarantined_rows,
                    "error_rows": error_rows,
                    "current_file": file_name,
                    "status": "processing",
                    "task_details": task_details  # ⭐ 新增：存储跳过文件数
                })
        
        # ⭐ v4.17.1新增：超时检查 - 在质量检查前检查
        if check_timeout():
            logger.warning(f"[BackgroundTask] 任务{task_id}在质量检查前超时，跳过质量检查")
        else:
            # ⭐ 数据质量Gate（批量同步完成后自动质量检查）
            # ⭐ v4.17.1修复：使用独立的数据库会话进行质量检查，避免事务错误影响主流程
            quality_check_result = None
            db_quality = None
            try:
                # ⭐ v4.18.2修复：使用异步会话查询成功文件
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
                
                # ⭐ v4.18.2修复：质量检查使用run_in_executor包装同步调用
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
                    
                    # 对每个平台+店铺组合进行质量检查（使用run_in_executor包装）
                    def _sync_quality_check(platform_shops_dict):
                        """同步质量检查函数"""
                        from backend.models.database import SessionLocal
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
                                        metric_date=datetime.now().date()
                                    )
                                    
                                    if check_result and not check_result.get("error"):
                                        quality_scores.append(check_result.get("data_quality_score", 0))
                                        missing_fields = check_result.get("missing_fields", [])  # ⭐ 修复：使用正确的字段名（check_b_class_completeness 返回的是 missing_fields，不是 missing_core_fields）
                                        if missing_fields:
                                            missing_fields_list.extend(missing_fields)
                                except Exception as check_error:
                                    # ⭐ v4.17.1修复：单个平台的质量检查失败不影响其他平台
                                    error_str = str(check_error)
                                    if 'InFailedSqlTransaction' in error_str or 'UndefinedColumn' in error_str:
                                        logger.warning(
                                            f"[BackgroundTask] 平台{info['platform_code']}质量检查失败（可能是表结构问题）: {check_error}"
                                        )
                                        # 回滚质量检查会话的事务
                                        try:
                                            db_quality.rollback()
                                        except Exception:
                                            pass
                                    else:
                                        logger.warning(
                                            f"[BackgroundTask] 平台{info['platform_code']}质量检查失败: {check_error}"
                                        )
                            
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
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # 保存质量检查结果到任务详情（使用主会话，异步）
                    await progress_tracker.update_task(task_id, {
                        "task_details": {
                            "quality_check": quality_check_result
                        }
                    })
                    
                    logger.info(f"[BackgroundTask] 数据质量检查完成: 平均评分={avg_quality_score:.2f}")
            except Exception as e:
                logger.warning(f"[BackgroundTask] 数据质量检查失败: {e}", exc_info=True)
                # ⭐ v4.17.1修复：确保质量检查会话回滚，不影响主流程
                if db_quality:
                    try:
                        db_quality.rollback()
                    except Exception:
                        pass
                # 质量检查失败不影响同步结果
            finally:
                # ⭐ v4.17.1修复：确保质量检查会话被关闭
                if db_quality:
                    try:
                        db_quality.close()
                    except Exception:
                        pass
        
        # 完成任务（更新最终统计信息）（异步）
        final_task_details = {
            "success_files": success_files,
            "failed_files": failed_files,
            "skipped_files": skipped_files
        }
        await progress_tracker.update_task(task_id, {
            "task_details": final_task_details
        })
        
        # 构建完成消息（包含跳过文件数）
        if skipped_files > 0:
            completion_message = f"成功{success_files}个，失败{failed_files}个，跳过{skipped_files}个"
        else:
            completion_message = f"成功{success_files}个，失败{failed_files}个"
        
        # ⭐ v4.17.1新增：检查是否因超时失败
        task_elapsed = (datetime.now() - task_start_time).total_seconds()
        if task_elapsed > TASK_TIMEOUT_SECONDS:
            completion_message = f"任务超时（已运行{task_elapsed:.1f}秒，超过限制{TASK_TIMEOUT_SECONDS}秒）: {completion_message}"
            logger.warning(f"[BackgroundTask] {completion_message}")
            await progress_tracker.complete_task(
                task_id,
                success=False,
                error=completion_message
            )
        else:
            await progress_tracker.complete_task(
                task_id,
                success=(failed_files == 0),
                error=None if failed_files == 0 else completion_message
            )
            logger.info(f"[BackgroundTask] 批量同步完成: {completion_message}（耗时{task_elapsed:.1f}秒）")
        
    except Exception as e:
        # ⭐ v4.15.0修复：捕获批量同步的整体异常，记录详细错误信息
        error_str = str(e)
        error_type = type(e).__name__
        
        # 构建详细的错误消息
        if 'InFailedSqlTransaction' in error_str or 'current transaction is aborted' in error_str.lower():
            error_message = f"批量同步失败：数据库事务错误 ({error_type}): {error_str}（可能是并发冲突或数据库连接问题）"
        else:
            error_message = f"批量同步失败 ({error_type}): {error_str}"
        
        logger.error(f"[BackgroundTask] {error_message}", exc_info=True)
        
        # 记录所有已处理的文件信息（异步）
        try:
            await progress_tracker.add_error(task_id, error_message)
        except Exception as add_error_err:
            logger.error(f"[BackgroundTask] 添加错误信息失败: {add_error_err}")
        
        # 完成任务（异步）
        try:
            await progress_tracker.complete_task(task_id, success=False, error=error_message)
        except Exception as complete_err:
            logger.error(f"[BackgroundTask] 完成任务失败: {complete_err}")
            # 如果complete_task也失败，至少记录日志
    finally:
        # ⭐ Phase 4.2: 减少用户任务计数（任务完成或失败时）
        if user_id:
            try:
                quota_service = get_user_task_quota_service()
                await quota_service.decrement_user_task_count(user_id)
            except Exception as quota_error:
                logger.warning(f"[BackgroundTask] 减少用户 {user_id} 任务计数失败: {quota_error}")
        
        # ⭐ v4.18.2修复：关闭主异步会话
        await db_main.close()


@router.post("/data-sync/batch")
@role_based_rate_limit(endpoint_type="data_sync")  # ⭐ v4.19.4: 基于角色的动态限流
async def sync_batch(
    body: BatchSyncRequest,  # ⭐ 修复：重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # ⭐ 修复：参数名必须为 request（slowapi 要求）
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    批量数据同步（使用 Celery 任务）
    
    v4.19.1 恢复：使用 Celery 任务队列执行数据同步
    - 任务持久化：任务存储在 Redis 中，服务器重启后自动恢复
    - 资源隔离：任务在独立的 Celery worker 进程中执行，不影响 API 服务
    - 降级处理：Celery 不可用时，降级到 asyncio.create_task()
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_{uuid.uuid4().hex[:8]}"
        
        # 查询待处理文件
        query = select(CatalogFile).where(
            CatalogFile.status == "pending"
        )
        
        # 平台筛选
        if body.platform and body.platform != "*":
            query = query.where(CatalogFile.platform_code == body.platform)
        
        # 数据域筛选
        if body.domains:
            query = query.where(CatalogFile.data_domain.in_(body.domains))
        
        # 粒度筛选
        if body.granularities:
            query = query.where(CatalogFile.granularity.in_(body.granularities))
        
        # 时间筛选（使用 UTC 时间）
        if body.since_hours:
            from datetime import timezone
            since_time = datetime.now(timezone.utc) - timedelta(hours=body.since_hours)
            query = query.where(CatalogFile.first_seen_at >= since_time)
        
        # 限制数量
        query = query.limit(body.limit)
        
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
        
        # ⭐ Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务（最多允许 {quota_service.max_concurrent_tasks} 个并发任务）",
                status_code=429  # Too Many Requests
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=total_files,
            task_type="bulk_ingest"
        )
        
        # v4.19.1: 提交 Celery 任务，添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # ⭐ Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # 动态并发数（最多20个并发）
            max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
            
            # ⭐ Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_batch_task.apply_async(
                args=(file_ids, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': True,  # BatchSyncRequest没有此字段，使用固定值True
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # ⭐ Phase 4.2: 添加用户ID（用于审计和配额管理）
                },
                priority=body.priority  # ⭐ Phase 4: 任务优先级（1-10，10最高）
            )
            
            logger.info(f"[API] 批量同步任务已提交: task_id={task_id}, 文件数={total_files}, celery_task_id={celery_task.id}")
            
            # 立即返回task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "total_files": total_files,
                    "processed_files": 0,
                },
                message=f"批量同步任务已提交，正在处理{total_files}个文件"
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # 动态并发数
                max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
                
                # ⭐ Phase 4.2: 增加用户任务计数（降级模式也需要配额管理）
                await quota_service.increment_user_task_count(user_id)
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=True,
                        max_concurrent=max_concurrent,
                        user_id=user_id  # ⭐ Phase 4.2: 传递用户ID
                    )
                )
                
                logger.info(f"[API] 批量同步任务已提交（降级模式）: task_id={task_id}, 文件数={total_files}")
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "fallback": True,
                        "message": "Celery不可用，使用降级模式"
                    },
                    message=f"批量同步任务已提交（降级模式），正在处理{total_files}个文件"
                )
            else:
                # 其他错误，重新抛出
                raise celery_error
        
    except Exception as e:
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
@role_based_rate_limit(endpoint_type="data_sync")  # ⭐ v4.19.4: 基于角色的动态限流
async def sync_batch_by_file_ids(
    body: BatchSyncByFileIdsRequest,  # ⭐ 修复：重命名为 body 避免与 slowapi 的 request 参数冲突
    request: Request,  # ⭐ 修复：参数名必须为 request（slowapi 要求）
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    批量数据同步（基于文件ID列表，使用 Celery 任务）
    
    v4.19.1 恢复：使用 Celery 任务队列执行数据同步
    - 任务持久化：任务存储在 Redis 中，服务器重启后自动恢复
    - 资源隔离：任务在独立的 Celery worker 进程中执行，不影响 API 服务
    - 降级处理：Celery 不可用时，降级到 asyncio.create_task()
    
    Args:
        file_ids: 文件ID列表（1-1000个）
        only_with_template: 是否只处理有模板的文件
        allow_quarantine: 是否允许隔离错误数据
        use_template_header_row: 是否使用模板表头行（严格模式）
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        
        # 生成task_id
        task_id = f"batch_ids_{uuid.uuid4().hex[:8]}"
        
        # 验证文件ID列表
        if not body.file_ids or len(body.file_ids) == 0:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件ID列表不能为空",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail="file_ids参数必填且不能为空",
                status_code=400
            )
        
        # 限制文件数量
        if len(body.file_ids) > 1000:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="文件数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=f"最多支持1000个文件，当前{len(body.file_ids)}个",
                status_code=400
            )
        
        # 验证文件是否存在
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id.in_(body.file_ids))
        )
        existing_files = result.scalars().all()
        
        existing_file_ids = [f.id for f in existing_files]
        missing_file_ids = set(body.file_ids) - set(existing_file_ids)
        
        if missing_file_ids:
            logger.warning(f"[API] 部分文件不存在: {missing_file_ids}")
            # 只处理存在的文件
            file_ids = existing_file_ids
        else:
            file_ids = body.file_ids
        
        total_files = len(file_ids)
        
        if total_files == 0:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="没有找到有效的文件",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"请求的文件ID都不存在: {body.file_ids}",
                status_code=404
            )
        
        # ⭐ Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务（最多允许 {quota_service.max_concurrent_tasks} 个并发任务）",
                status_code=429  # Too Many Requests
            )
        
        # 创建进度任务
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=total_files,
            task_type="batch_ingest"
        )
        
        # v4.19.1: 提交 Celery 任务，添加降级处理
        try:
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # ⭐ Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # 动态并发数（最多20个并发）
            max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
            
            # ⭐ Phase 4: 使用 apply_async 支持优先级参数
            celery_task = sync_batch_task.apply_async(
                args=(file_ids, task_id),
                kwargs={
                    'only_with_template': body.only_with_template,
                    'allow_quarantine': body.allow_quarantine,
                    'use_template_header_row': body.use_template_header_row,
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # ⭐ Phase 4.2: 添加用户ID（用于审计和配额管理）
                },
                priority=body.priority  # ⭐ Phase 4: 任务优先级（1-10，10最高）
            )
            
            logger.info(f"[API] 批量同步任务已提交: task_id={task_id}, 文件数={total_files}, celery_task_id={celery_task.id}")
            
            # 立即返回task_id
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "total_files": total_files,
                    "processed_files": 0,
                    "missing_file_ids": list(missing_file_ids) if missing_file_ids else None
                },
                message=f"批量同步任务已提交，正在处理{total_files}个文件"
            )
        except Exception as celery_error:
            # Celery任务提交失败时的降级处理
            error_type = type(celery_error).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type or "redis" in str(celery_error).lower():
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # 动态并发数
                max_concurrent = min(20, max(5, len(file_ids) // 10 + 1))
                
                # 降级到 asyncio.create_task()
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=file_ids,
                        task_id=task_id,
                        only_with_template=body.only_with_template,
                        allow_quarantine=body.allow_quarantine,
                        use_template_header_row=body.use_template_header_row,
                        max_concurrent=max_concurrent
                    )
                )
                
                logger.info(f"[API] 批量同步任务已提交（降级模式）: task_id={task_id}, 文件数={total_files}")
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "total_files": total_files,
                        "processed_files": 0,
                        "fallback": True,
                        "missing_file_ids": list(missing_file_ids) if missing_file_ids else None,
                        "message": "Celery不可用，使用降级模式"
                    },
                    message=f"批量同步任务已提交（降级模式），正在处理{total_files}个文件"
                )
            else:
                # 其他错误，重新抛出
                raise celery_error
        
    except Exception as e:
        logger.error(f"[API] 批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量同步失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/progress/{task_id}")
async def get_sync_progress(
    task_id: str,
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    获取同步进度
    
    查询指定任务的同步进度信息。
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        # ⭐ v4.18.2修复：确保使用干净的事务（先回滚任何失败的事务）
        try:
            await db.rollback()
        except:
            pass  # 如果没有活动事务，忽略错误
        
        progress_tracker = SyncProgressTracker(db)
        task_info = await progress_tracker.get_task(task_id)
        
        if not task_info:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"任务{task_id}不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查任务ID是否正确，或查看任务列表确认任务是否存在",
                status_code=404
            )
        
        return success_response(data=task_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 获取同步进度失败: {e}", exc_info=True)
        # ⭐ v4.18.2修复：确保异常时回滚事务
        try:
            await db.rollback()
        except:
            pass
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取同步进度失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/tasks")
async def list_sync_tasks(
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    列出所有同步任务
    
    查询所有同步任务列表，支持状态筛选。
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        progress_tracker = SyncProgressTracker(db)
        tasks = await progress_tracker.list_tasks(status=status, limit=limit)
        
        return success_response(
            data=tasks,
            message=f"共找到{len(tasks)}个任务"
        )
        
    except Exception as e:
        logger.error(f"[API] 列出同步任务失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出同步任务失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/loss-analysis")
async def analyze_data_loss_endpoint(
    file_id: Optional[int] = Query(None, description="文件ID"),
    task_id: Optional[str] = Query(None, description="任务ID"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    分析数据丢失情况
    
    功能：
    - 统计各层数据数量（Raw、Staging、Fact、Quarantine）
    - 计算数据丢失率
    - 分析丢失数据的共同特征
    - 识别丢失位置（Raw→Staging、Staging→Fact）
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        # ⭐ v4.18.2：使用异步版本
        result = await async_analyze_data_loss(db, file_id, task_id, data_domain)
        
        if not result.get("success"):
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message="分析数据丢失失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=result.get("error"),
                recovery_suggestion="请检查查询参数和数据库连接，或联系系统管理员",
                status_code=500
            )
        
        return success_response(
            data=result,
            message="数据丢失分析完成"
        )
    
    except Exception as e:
        logger.error(f"[API] 分析数据丢失失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="分析数据丢失失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/loss-alert")
async def check_data_loss_alert(
    file_id: Optional[int] = Query(None, description="文件ID"),
    task_id: Optional[str] = Query(None, description="任务ID"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    threshold: float = Query(5.0, description="丢失率阈值（%）", ge=0, le=100),
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    检查数据丢失预警
    
    功能：
    - 检查数据丢失率是否超过阈值
    - 如果超过阈值，返回预警信息
    - 提供丢失数据统计和特征分析
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        # ⭐ v4.18.2：使用异步版本
        result = await async_check_data_loss_threshold(db, file_id, task_id, data_domain, threshold)
        
        if not result.get("success"):
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message="检查数据丢失预警失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=result.get("error"),
                recovery_suggestion="请检查查询参数和数据库连接，或联系系统管理员",
                status_code=500
            )
        
        return success_response(
            data=result,
            message=result.get("message", "检查完成")
        )
    
    except Exception as e:
        logger.error(f"[API] 检查数据丢失预警失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检查数据丢失预警失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查查询参数和数据库连接，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/platforms")
async def get_available_platforms(
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    获取可用的平台列表 ⭐ **新增（2025-02-01）**
    
    功能：
    - 从catalog_files表中获取所有有文件的平台
    - 用于动态加载平台选项
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        # 查询所有有文件的平台（⭐ v4.18.2：使用 await）
        result = await db.execute(
            select(distinct(CatalogFile.platform_code))
            .where(CatalogFile.platform_code.isnot(None))
            .order_by(CatalogFile.platform_code)
        )
        platforms = result.scalars().all()
        
        return success_response(
            data={"platforms": [p for p in platforms if p]},
            message="获取平台列表成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Platforms] 获取平台列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取平台列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/governance/detailed-coverage")
async def get_detailed_template_coverage(
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    获取详细的模板覆盖统计 ⭐ **新增（2025-02-01）**
    
    功能：
    - 按平台、数据域、子类型、粒度统计模板覆盖情况
    - 检测需要更新的模板（表头字段变化）
    - 返回详细的覆盖和缺失清单
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        from backend.services.template_matcher import get_template_matcher
        
        template_matcher = get_template_matcher(db)
        
        # ⭐ v4.15.0修复：基于所有模板统计，而不是只基于待同步文件
        # 1. 查询所有模板（published状态）（⭐ v4.18.2：使用 await）
        from modules.core.db import FieldMappingTemplate
        templates_stmt = select(FieldMappingTemplate).where(
            FieldMappingTemplate.status == 'published'
        )
        templates_result = await db.execute(templates_stmt)
        all_templates = templates_result.scalars().all()
        
        # 2. 从模板构建唯一组合（平台+数据域+子类型+粒度）
        template_combinations = {}
        for template in all_templates:
            key = (
                template.platform,
                template.data_domain,
                template.sub_domain or None,
                template.granularity
            )
            if key not in template_combinations:
                template_combinations[key] = {
                    'platform': template.platform,
                    'domain': template.data_domain,
                    'sub_domain': template.sub_domain,
                    'granularity': template.granularity,
                    'template': template
                }
        
        # 3. 查询所有文件的唯一组合（包括pending和ingested，用于统计文件数）
        files_stmt = select(
            CatalogFile.platform_code,
            CatalogFile.data_domain,
            CatalogFile.sub_domain,
            CatalogFile.granularity
        ).where(
            CatalogFile.platform_code.isnot(None),
            CatalogFile.data_domain.isnot(None),
            CatalogFile.granularity.isnot(None),
            CatalogFile.status.in_(['pending', 'ingested'])  # ⭐ 包括已同步的文件
        ).distinct()
        
        # ⭐ v4.18.2：使用 await
        file_combinations_result = await db.execute(files_stmt)
        all_file_combinations_raw = file_combinations_result.all()
        
        # 4. 合并模板组合和文件组合（确保统计完整）
        all_combinations_dict = {}
        
        # 先添加模板组合
        for key, combo in template_combinations.items():
            all_combinations_dict[key] = (
                combo['platform'],
                combo['domain'],
                combo['sub_domain'],
                combo['granularity']
            )
        
        # 再添加文件组合（如果不在模板组合中）
        for platform, domain, sub_domain, granularity in all_file_combinations_raw:
            key = (platform, domain, sub_domain or None, granularity)
            if key not in all_combinations_dict:
                all_combinations_dict[key] = (platform, domain, sub_domain, granularity)
        
        all_combinations = list(all_combinations_dict.values())
        
        # 2. 统计覆盖情况
        covered_list = []
        missing_list = []
        needs_update_list = []
        
        for platform, domain, sub_domain, granularity in all_combinations:
            if not platform or not domain or not granularity:
                continue
            
            # 查找模板（⭐ v4.18.2：添加 await）
            template = await template_matcher.find_best_template(
                platform=platform,
                data_domain=domain,
                granularity=granularity,
                sub_domain=sub_domain
            )
            
            # ⭐ v4.15.0修复：统计该组合的文件数（包括pending和ingested）
            # ⭐ v4.18.2：使用 await
            file_count_stmt = select(func.count(CatalogFile.id)).where(
                CatalogFile.platform_code == platform,
                CatalogFile.data_domain == domain,
                CatalogFile.granularity == granularity,
                CatalogFile.sub_domain == sub_domain,
                CatalogFile.status.in_(['pending', 'ingested'])  # ⭐ 包括已同步的文件
            )
            file_count_result = await db.execute(file_count_stmt)
            file_count = file_count_result.scalar() or 0
            
            combo_info = {
                'platform': platform,
                'domain': domain,
                'sub_domain': sub_domain or 'N/A',
                'granularity': granularity,
                'file_count': file_count
            }
            
            if template:
                # 检查模板是否需要更新（通过检测最近文件的表头变化）
                needs_update = False
                update_reason = None
                
                # ⭐ v4.15.0修复：获取该组合的一个示例文件（优先pending，其次ingested）
                # ⭐ v4.18.2：使用 await
                sample_file_result = await db.execute(
                    select(CatalogFile).where(
                        CatalogFile.platform_code == platform,
                        CatalogFile.data_domain == domain,
                        CatalogFile.granularity == granularity,
                        CatalogFile.sub_domain == sub_domain,
                        CatalogFile.status.in_(['pending', 'ingested'])  # ⭐ 包括已同步的文件
                    ).order_by(
                        # 优先pending，其次ingested
                        CatalogFile.status.desc()  # 'pending' > 'ingested' (字母序)
                    ).limit(1)
                )
                sample_file = sample_file_result.scalar_one_or_none()
                
                if sample_file:
                    try:
                        from backend.services.excel_parser import ExcelParser
                        import pandas as pd
                        
                        # ⭐ v4.18.2修复：使用 run_in_executor 包装文件读取，避免阻塞事件循环
                        loop = asyncio.get_running_loop()
                        df = await loop.run_in_executor(
                            None,
                            ExcelParser.read_excel,
                            sample_file.file_path,
                            template.header_row or 0,
                            1  # nrows=1
                        )
                        current_columns = df.columns.tolist()
                        
                        # 检测表头变化（⭐ v4.18.2：添加 await）
                        header_changes = await template_matcher.detect_header_changes(
                            template_id=template.id,
                            current_columns=current_columns
                        )
                        
                        if header_changes.get('detected') and header_changes.get('match_rate', 100) < 90:
                            needs_update = True
                            added = header_changes.get('added_fields', [])
                            removed = header_changes.get('removed_fields', [])
                            if added or removed:
                                update_reason = f"新增{len(added)}个字段，删除{len(removed)}个字段"
                            else:
                                update_reason = f"匹配率{header_changes.get('match_rate', 0):.1f}%"
                    except Exception as e:
                        logger.warning(f"[DetailedCoverage] 检测模板更新失败: {e}")
                
                covered_list.append({
                    **combo_info,
                    'template_id': template.id,
                    'template_name': template.template_name,
                    'template_version': template.version,
                    'needs_update': needs_update,
                    'update_reason': update_reason
                })
                
                if needs_update:
                    needs_update_list.append({
                        **combo_info,
                        'template_id': template.id,
                        'template_name': template.template_name,
                        'update_reason': update_reason
                    })
            else:
                missing_list.append(combo_info)
        
        # 3. 计算统计
        # ⭐ v4.15.0修复：覆盖率应该基于所有模板，而不是基于文件组合
        # total_combinations = 所有模板数 + 缺少模板的文件组合数
        total_combinations = len(template_combinations) + len(missing_list)
        covered_count = len(covered_list)
        missing_count = len(missing_list)
        needs_update_count = len(needs_update_list)
        
        # ⭐ v4.15.0修复：覆盖率 = 有模板的组合数 / 总组合数
        # 总组合数 = 所有模板数（已覆盖）+ 缺少模板的文件组合数（未覆盖）
        coverage_percentage = (len(template_combinations) / total_combinations * 100) if total_combinations > 0 else 0
        
        return success_response(
            data={
                'summary': {
                    'total_combinations': total_combinations,
                    'covered_count': covered_count,
                    'missing_count': missing_count,
                    'needs_update_count': needs_update_count,
                    'coverage_percentage': round(coverage_percentage, 1)
                },
                'covered': covered_list,
                'missing': missing_list,
                'needs_update': needs_update_list
            },
            message="获取详细模板覆盖统计成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync DetailedCoverage] 获取详细统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取详细模板覆盖统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接，或联系系统管理员",
            status_code=500
        )


@router.get("/data-sync/governance/stats")
async def get_governance_stats(
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    数据治理统计API ⭐ **新增（2025-02-01）**
    
    功能：
    - 统计待同步文件数量
    - 统计已同步文件数量
    - 用于数据治理概览显示
    
    v4.18.1修复：所有统计都从数据库查询，保持数据一致性
    - pending_count: 查询 status='pending' 的文件数
    - ingested_count: 查询 status='ingested' 的文件数
    - 解决问题：同步后待同步数量不减少的问题
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    """
    try:
        # ⭐ v4.18.1修复：统一从数据库查询，保持数据一致性
        # 之前的问题：pending_count通过文件系统扫描，ingested_count通过数据库查询
        # 导致同步后，pending_count不减少（因为文件仍在文件系统中）
        
        # ⭐ v4.18.2：使用 await 进行异步查询
        # 统计待同步文件（status='pending'）
        pending_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'pending')
        )
        pending_count = pending_result.scalar() or 0
        
        # 统计已同步文件（status='ingested'）
        ingested_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'ingested')
        )
        ingested_count = ingested_result.scalar() or 0
        
        # ⭐ v4.17.2修复：单独统计失败文件（status='failed'），用于显示失败文件数
        failed_result = await db.execute(
            select(func.count(CatalogFile.id)).where(CatalogFile.status == 'failed')
        )
        failed_count = failed_result.scalar() or 0
        
        # ⭐ v4.17.2新增：统计各状态的详细数量（用于调试和显示）
        status_counts = {}
        for status_name in ['pending', 'partial_success', 'failed', 'quarantined', 'needs_shop', 'ingested', 'processing']:
            count_result = await db.execute(
                select(func.count(CatalogFile.id)).where(CatalogFile.status == status_name)
            )
            count = count_result.scalar() or 0
            if count > 0:
                status_counts[status_name] = count
        
        # 计算总文件数（所有已注册的文件）
        total_result = await db.execute(select(func.count(CatalogFile.id)))
        total_count = total_result.scalar() or 0
        
        return success_response(
            data={
                "pending_count": pending_count,  # ⭐ v4.18.1修复：从数据库查询status='pending'
                "ingested_count": ingested_count,
                "failed_count": failed_count,  # 仅failed状态的文件数
                "total_count": total_count,  # ⭐ v4.18.1修复：总文件数从数据库查询
                "status_counts": status_counts  # ⭐ 各状态的详细数量
            },
            message="数据治理统计查询成功"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Governance] 查询统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询数据治理统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接，或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/batch-all")
@role_based_rate_limit(endpoint_type="data_sync")  # ⭐ v4.19.4: 基于角色的动态限流
async def sync_all_with_template(
    request: Request,  # ⭐ 修复：参数名必须为 request（slowapi 要求）
    db: AsyncSession = Depends(get_async_db),  # ⭐ v4.18.2：改为异步会话
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    手动全部数据同步API ⭐ **新增（2025-02-01）**
    
    功能：
    - 同步所有有模板的待同步文件
    - 后台任务执行，返回任务ID
    - 用于文件列表页面的"手动全部数据同步"按钮
    
    v4.18.2: 迁移到异步会话（AsyncSession）
    v4.18.2修复：使用 asyncio.create_task() 替代 BackgroundTasks，避免阻塞事件循环
    """
    try:
        from backend.services.template_matcher import get_template_matcher
        
        # 1. 查询所有待同步文件（⭐ v4.18.2：使用 await）
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.status == 'pending')
        )
        pending_files = result.scalars().all()
        
        # 2. 筛选有模板的文件
        template_matcher = get_template_matcher(db)
        files_with_template = []
        
        for file_record in pending_files:
            # ⭐ v4.18.2：添加 await
            template = await template_matcher.find_best_template(
                platform=file_record.platform_code or "",
                data_domain=file_record.data_domain or "",
                granularity=file_record.granularity or "",
                sub_domain=file_record.sub_domain
            )
            if template:
                files_with_template.append(file_record.id)
        
        if not files_with_template:
            return success_response(
                data={"task_id": None, "file_count": 0},
                message="没有找到有模板的待同步文件"
            )
        
        # 3. 创建批量同步任务
        task_id = f"batch_all_{uuid.uuid4().hex[:8]}"
        progress_tracker = SyncProgressTracker(db)
        
        # ⭐ Phase 4.2: 检查用户任务配额
        user_id = current_user.user_id
        quota_service = get_user_task_quota_service()
        can_submit, error_message = await quota_service.can_submit_task(user_id)
        if not can_submit:
            return error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="任务数量超过限制",
                error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
                detail=error_message,
                recovery_suggestion=f"请等待当前任务完成后再提交新任务（最多允许 {quota_service.max_concurrent_tasks} 个并发任务）",
                status_code=429  # Too Many Requests
            )
        
        # 初始化任务（使用正确的参数）（v4.18.2改为异步）
        await progress_tracker.create_task(
            task_id=task_id,
            total_files=len(files_with_template),
            task_type="batch_sync_all"
        )
        
        # ⭐ v4.19.0修复：使用 Celery 任务替代 asyncio.create_task()
        max_concurrent = min(20, max(5, len(files_with_template) // 10 + 1))
        
        try:
            # ⭐ v4.19.8修复：添加缺失的导入语句
            from backend.tasks.data_sync_tasks import sync_batch_task
            
            # ⭐ Phase 4.2: 增加用户任务计数
            await quota_service.increment_user_task_count(user_id)
            
            # ⭐ Phase 4: 使用 apply_async 支持优先级参数（batch-all 使用默认优先级 5）
            celery_task = sync_batch_task.apply_async(
                args=(files_with_template, task_id),
                kwargs={
                    'only_with_template': True,
                    'allow_quarantine': True,
                    'use_template_header_row': True,
                    'max_concurrent': max_concurrent,
                    'user_id': user_id  # ⭐ Phase 4.2: 添加用户ID（用于审计和配额管理）
                },
                priority=5  # ⭐ Phase 4: batch-all 使用默认优先级
            )
            
            return success_response(
                data={
                    "task_id": task_id,
                    "celery_task_id": celery_task.id,
                    "file_count": len(files_with_template),
                    "message": f"已启动批量同步任务，共{len(files_with_template)}个文件"
                },
                message=f"批量同步任务已启动（{len(files_with_template)}个文件）"
            )
        except Exception as e:
            # ⭐ 修复：Celery任务提交失败时的降级处理
            error_type = type(e).__name__
            if "OperationalError" in error_type or "ConnectionError" in error_type:
                # Redis连接失败，降级到 asyncio.create_task()
                logger.warning(f"[API] Redis/Celery连接失败（{error_type}），降级到 asyncio.create_task()")
                
                # ⭐ Phase 4.2: 增加用户任务计数（降级模式也需要配额管理）
                await quota_service.increment_user_task_count(user_id)
                
                asyncio.create_task(
                    process_batch_sync_background(
                        file_ids=files_with_template,
                        task_id=task_id,
                        only_with_template=True,
                        allow_quarantine=True,
                        use_template_header_row=True,
                        max_concurrent=max_concurrent,
                        user_id=user_id  # ⭐ Phase 4.2: 传递用户ID
                    )
                )
                
                return success_response(
                    data={
                        "task_id": task_id,
                        "file_count": len(files_with_template),
                        "fallback": True,
                        "message": f"已启动批量同步任务（降级模式），共{len(files_with_template)}个文件"
                    },
                    message=f"批量同步任务已启动（降级模式，{len(files_with_template)}个文件）"
                )
            else:
                # 其他错误，重新抛出
                raise
        
    except Exception as e:
        logger.error(f"[DataSync BatchAll] 启动批量同步失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="启动批量同步失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            recovery_suggestion="请检查系统状态，或联系系统管理员",
            status_code=500
        )


@router.post("/data-sync/cleanup-database")
async def cleanup_database(
    db: AsyncSession = Depends(get_async_db)  # ⭐ v4.18.2：改为异步会话
):
    """
    清理数据库API ⭐ **新增（2025-02-01）**
    
    功能：
    - 清理所有已入库的数据（B类数据表）
    - 重置文件状态为pending
    - 用于测试环境数据清理
    
    v4.18.2: 迁移到异步会话（使用run_in_executor包装DDL操作）
    """
    try:
        # ⭐ v4.18.2：由于inspect()需要同步引擎，使用run_in_executor包装整个操作
        def _sync_cleanup():
            """同步执行清理操作"""
            from sqlalchemy import inspect, text
            
            sync_db = SessionLocal()
            try:
                inspector = inspect(sync_db.bind)
                
                # 查询b_class schema中所有表
                all_tables = inspector.get_table_names(schema='b_class')
                
                # 筛选出所有以fact_开头的表（B类数据表）
                fact_tables = [t for t in all_tables if t.startswith('fact_')]
                
                if not fact_tables:
                    logger.info("[DataSync Cleanup] b_class schema中没有找到fact_开头的表")
                    fact_tables = []
                
                deleted_counts = {}
                for table_name in fact_tables:
                    try:
                        # 统计行数
                        count_sql = text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
                        count = sync_db.execute(count_sql).scalar() or 0
                        
                        # 使用DELETE删除数据（保留表结构）
                        if count > 0:
                            delete_sql = text(f'DELETE FROM b_class."{table_name}"')
                            sync_db.execute(delete_sql)
                            logger.info(f"[DataSync Cleanup] 删除表 b_class.{table_name}: {count} 行")
                        else:
                            logger.debug(f"[DataSync Cleanup] 表 b_class.{table_name} 无数据，跳过删除")
                        
                        deleted_counts[table_name] = count
                        
                    except Exception as table_error:
                        # 单个表清理失败不影响其他表
                        logger.error(f"[DataSync Cleanup] 清理表 b_class.{table_name} 失败: {table_error}", exc_info=True)
                        deleted_counts[table_name] = -1  # 使用-1表示失败
                
                # 2. 重置所有已入库文件状态为pending（包括ingested、partial_success、processing、failed）
                from sqlalchemy import select, update
                # ⭐ v4.18.2修复：使用select查询替代db.query()
                result = sync_db.execute(
                    select(CatalogFile).where(
                        CatalogFile.status.in_(['ingested', 'partial_success', 'processing', 'failed'])
                    )
                )
                files_to_reset = result.scalars().all()
                
                status_distribution = {}
                for file_record in files_to_reset:
                    status = file_record.status
                    status_distribution[status] = status_distribution.get(status, 0) + 1
                
                # 批量更新文件状态为pending
                # ⭐ v4.18.2修复：使用update语句替代db.query().update()
                update_stmt = update(CatalogFile).where(
                    CatalogFile.status.in_(['ingested', 'partial_success', 'processing', 'failed'])
                ).values(status="pending")
                result = sync_db.execute(update_stmt)
                updated_count = result.rowcount
                
                # 3. 提交事务
                sync_db.commit()
                
                total_deleted = sum(v for v in deleted_counts.values() if v > 0)
                
                logger.info(f"[DataSync Cleanup] 清理完成: 删除{total_deleted}行数据，重置{updated_count}个文件状态为pending（状态分布: {status_distribution}）")
                
                return {
                    "deleted_counts": deleted_counts,
                    "total_deleted_rows": total_deleted,
                    "reset_files_count": updated_count,
                    "status_distribution": status_distribution
                }
            except Exception as e:
                sync_db.rollback()
                raise
            finally:
                sync_db.close()
        
        # 在线程池中执行同步操作
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _sync_cleanup)
        
        return success_response(
            data=result,
            message=f"数据库清理完成：删除{result['total_deleted_rows']}行数据，重置{result['reset_files_count']}个文件状态为pending"
        )
        
    except Exception as e:
        logger.error(f"[DataSync Cleanup] 清理数据库失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理数据库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


# ⭐ Phase 1.4.3: 任务状态管理 API
@router.get("/data-sync/task-status/{celery_task_id}", response_model=CeleryTaskStatusResponse)
async def get_celery_task_status(
    celery_task_id: str = Path(..., description="Celery 任务ID")
):
    """
    查询 Celery 任务状态
    
    根据 Celery 任务ID查询任务状态、结果和错误信息。
    
    Args:
        celery_task_id: Celery 任务ID（从任务提交响应中获取的 celery_task_id）
    
    Returns:
        CeleryTaskStatusResponse: 任务状态信息
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        
        # 创建 AsyncResult 对象
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 获取任务状态
        state = task_result.state
        ready = task_result.ready()
        successful = task_result.successful() if ready else None
        
        # 获取任务结果和错误信息
        result = None
        traceback = None
        if ready:
            if successful:
                try:
                    result = task_result.result
                except Exception as e:
                    logger.warning(f"[API] 获取任务结果失败: {e}")
                    result = None
            else:
                try:
                    traceback = task_result.traceback
                except Exception as e:
                    logger.warning(f"[API] 获取任务错误信息失败: {e}")
                    traceback = None
        
        # 获取任务详细信息
        # ⭐ 修复：info 可能是异常对象，需要转换为字典或 None
        info = None
        if hasattr(task_result, 'info') and task_result.info is not None:
            if isinstance(task_result.info, dict):
                info = task_result.info
            elif isinstance(task_result.info, Exception):
                # 如果是异常对象，转换为错误信息字典
                info = {"error": str(task_result.info), "error_type": type(task_result.info).__name__}
            else:
                # 其他类型，尝试转换为字符串
                try:
                    info = {"value": str(task_result.info)}
                except Exception:
                    info = None
        
        # 构建响应
        return CeleryTaskStatusResponse(
            celery_task_id=celery_task_id,
            state=state,
            ready=ready,
            successful=successful,
            result=result,
            traceback=traceback,
            info=info
        )
        
    except Exception as e:
        logger.error(f"[API] 查询 Celery 任务状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"查询任务状态失败: {str(e)}"
        )


@router.delete("/data-sync/cancel-task/{celery_task_id}", response_model=CancelTaskResponse)
async def cancel_celery_task(
    celery_task_id: str = Path(..., description="Celery 任务ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    取消 Celery 任务
    
    撤销正在执行或等待执行的 Celery 任务。
    
    Args:
        celery_task_id: Celery 任务ID（从任务提交响应中获取的 celery_task_id）
    
    Returns:
        CancelTaskResponse: 取消操作结果
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        import asyncio
        
        # 创建 AsyncResult 对象
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 检查任务状态
        state = task_result.state
        
        # 只能取消 PENDING 或 STARTED 状态的任务
        if state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            raise HTTPException(
                status_code=400,
                detail=f"无法取消已完成的任务（当前状态: {state}）"
            )
        
        # 撤销任务
        celery_app.control.revoke(celery_task_id, terminate=True)
        
        # 等待一小段时间确认撤销
        await asyncio.sleep(0.5)
        
        # 检查撤销是否成功
        task_result = AsyncResult(celery_task_id, app=celery_app)
        revoked = task_result.state == 'REVOKED'
        
        logger.info(f"[API] 任务已撤销: celery_task_id={celery_task_id}, state={task_result.state}")
        
        return CancelTaskResponse(
            celery_task_id=celery_task_id,
            message="任务已成功撤销" if revoked else "任务撤销请求已发送",
            revoked=revoked
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 取消 Celery 任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"取消任务失败: {str(e)}"
        )


@router.post("/data-sync/retry-task/{celery_task_id}", response_model=RetryTaskResponse)
async def retry_celery_task(
    celery_task_id: str = Path(..., description="Celery 任务ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)  # ⭐ Phase 4.2: 用户认证
):
    """
    重试 Celery 任务
    
    对于失败的任务，重新提交执行。会创建新的 Celery 任务。
    
    ⚠️ 注意：当前实现暂不支持直接重试，需要从数据库查询原始任务参数。
    建议使用原始 API 端点重新提交任务。
    
    Args:
        celery_task_id: 原始 Celery 任务ID
    
    Returns:
        RetryTaskResponse: 重试操作结果（包含新的任务ID）
    """
    try:
        from celery.result import AsyncResult
        from backend.celery_app import celery_app
        
        # 获取原始任务信息
        task_result = AsyncResult(celery_task_id, app=celery_app)
        
        # 检查任务状态
        state = task_result.state
        
        # 只能重试失败的任务
        if state != 'FAILURE':
            raise HTTPException(
                status_code=400,
                detail=f"只能重试失败的任务（当前状态: {state}）"
            )
        
        # TODO: 实现完整的重试逻辑
        # 1. 从数据库查询原始任务参数（需要维护 celery_task_id 到任务参数的映射）
        # 2. 使用相同参数创建新任务
        # 3. 返回新的任务ID
        
        # 当前实现：返回提示信息
        return RetryTaskResponse(
            original_celery_task_id=celery_task_id,
            new_celery_task_id=None,
            new_task_id=None,
            message="重试功能需要原始任务参数，当前实现暂不支持。请使用原始 API 端点重新提交任务。"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 重试 Celery 任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"重试任务失败: {str(e)}"
        )

