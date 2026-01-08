"""
数据采集模块 API 路由

提供采集配置、任务管理、账号管理等API端点

v4.18.0: Pydantic模型已迁移到backend/schemas/collection.py（Contract-First架构）
"""

import uuid
import asyncio
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, select

from backend.models.database import get_db, get_async_db
from modules.core.db import CollectionConfig, CollectionTask, CollectionTaskLog
from modules.core.logger import get_logger
# v4.7.4: 移除 WebSocket，统一使用 HTTP 轮询

# v4.18.0: 导入schemas（Contract-First架构）
from backend.schemas.collection import (
    CollectionConfigCreate,
    CollectionConfigUpdate,
    CollectionConfigResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskLogResponse,
    CollectionAccountResponse,
    TaskHistoryResponse,
    TaskStatsResponse,
    DailyStats,
    ScheduleUpdateRequest,
    CronValidateRequest,
    ScheduleResponse,
    ScheduleInfoResponse,
    CronValidationResponse,
    CronPresetsResponse,
    ScheduledJobsResponse,
    HealthCheckResponse,
)
from backend.schemas.common import SuccessResponse

logger = get_logger(__name__)

router = APIRouter(tags=["数据采集"])


# ============================================================
# 配置管理 API
# ============================================================

@router.get("/configs", response_model=List[CollectionConfigResponse])
async def list_configs(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集配置列表"""
    stmt = select(CollectionConfig)
    
    if platform:
        stmt = stmt.where(CollectionConfig.platform == platform)
    
    if is_active is not None:
        stmt = stmt.where(CollectionConfig.is_active == is_active)
    
    stmt = stmt.order_by(desc(CollectionConfig.created_at))
    result = await db.execute(stmt)
    configs = result.scalars().all()
    return configs


@router.post("/configs", response_model=CollectionConfigResponse)
async def create_config(
    config: CollectionConfigCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建采集配置（v4.7.0 - 支持自动生成配置名）"""
    # v4.7.0: 自动生成配置名（如果未提供）
    config_name = config.name
    if not config_name:
        # 格式: {platform}-{domains}-v{n}
        domains_str = "-".join(sorted(config.data_domains))
        base_name = f"{config.platform}-{domains_str}"
        
        # 查找现有版本号
        stmt = select(CollectionConfig).where(
            CollectionConfig.name.like(f"{base_name}-v%"),
            CollectionConfig.platform == config.platform
        )
        result = await db.execute(stmt)
        existing_configs = result.scalars().all()
        
        existing_versions = []
        for cfg in existing_configs:
            # 提取版本号
            if cfg.name.startswith(base_name + "-v"):
                try:
                    version_str = cfg.name[len(base_name)+2:]  # 跳过 "-v"
                    existing_versions.append(int(version_str))
                except ValueError:
                    pass
        
        # 生成新版本号
        next_version = max(existing_versions, default=0) + 1
        config_name = f"{base_name}-v{next_version}"
        
        logger.info(f"Auto-generated config name: {config_name}")
    else:
        # 检查名称是否重复
        stmt = select(CollectionConfig).where(
            CollectionConfig.name == config_name,
            CollectionConfig.platform == config.platform
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=400, detail="配置名称已存在")
    
    # 验证数据域
    valid_domains = ["orders", "products", "services", "analytics", "finance", "inventory"]
    for domain in config.data_domains:
        if domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"无效的数据域: {domain}")
    
    # v4.7.0: 验证 account_ids（空数组表示所有活跃账号）
    if len(config.account_ids) == 0:
        logger.info(f"Config uses all active accounts for platform: {config.platform}")
    
    db_config = CollectionConfig(
        name=config_name,
        platform=config.platform,
        account_ids=config.account_ids,
        data_domains=config.data_domains,
        sub_domains=config.sub_domains,  # v4.7.0: 子域数组
        granularity=config.granularity,
        date_range_type=config.date_range_type,
        custom_date_start=config.custom_date_start,
        custom_date_end=config.custom_date_end,
        schedule_enabled=config.schedule_enabled,
        schedule_cron=config.schedule_cron,
        retry_count=config.retry_count,
    )
    
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    
    logger.info(f"Created collection config: {db_config.name} ({db_config.platform}) with {len(db_config.data_domains)} domains")
    return db_config


@router.get("/configs/{config_id}", response_model=CollectionConfigResponse)
async def get_config(
    config_id: int = Path(..., description="配置ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集配置详情"""
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    return config


@router.put("/configs/{config_id}", response_model=CollectionConfigResponse)
async def update_config(
    config_id: int,
    update_data: CollectionConfigUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新采集配置"""
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    # 更新非空字段
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            setattr(config, key, value)
    
    await db.commit()
    await db.refresh(config)
    
    logger.info(f"Updated collection config: {config.name}")
    return config


@router.delete("/configs/{config_id}", response_model=SuccessResponse[None])
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除采集配置"""
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    await db.delete(config)
    await db.commit()
    
    logger.info(f"Deleted collection config: {config.name}")
    return SuccessResponse(success=True, message="配置已删除")


# ============================================================
# 账号 API
# ============================================================

@router.get("/accounts", response_model=List[CollectionAccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None  # [*] Phase 3: 用于获取缓存服务
):
    """
    获取账号列表（脱敏）
    
    v4.7.0: 从数据库读取账号信息，返回脱敏后的数据
    [*] Phase 3: 添加缓存支持（5分钟TTL）
    """
    # [*] Phase 3: 尝试从缓存获取
    if request and hasattr(request.app.state, 'cache_service'):
        cache_service = request.app.state.cache_service
        cached_data = await cache_service.get("accounts_list", platform=platform)
        if cached_data is not None:
            logger.debug(f"[Cache] 账号列表缓存命中: platform={platform}")
            return cached_data
    
    try:
        # #region agent log
        import json
        from modules.core.path_manager import get_project_root
        debug_log_path = get_project_root() / ".cursor" / "debug.log"
        with open(debug_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'location':'collection.py:list_accounts:start','message':'List accounts API called','data':{'platform':platform},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H2'})+'\n')
        # #endregion
        
        from backend.services.account_loader_service import get_account_loader_service
        
        account_loader = get_account_loader_service()
        accounts = account_loader.load_all_accounts(db, platform=platform)
        
        # #region agent log
        with open(debug_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'location':'collection.py:list_accounts:loaded','message':'Accounts loaded from service','data':{'count':len(accounts),'firstAccount':accounts[0] if accounts else None},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H2'})+'\n')
        # #endregion
        
        # 转换为API响应格式
        result = []
        for account in accounts:
            result.append(CollectionAccountResponse(
                id=account.get("account_id", "unknown"),
                name=account.get("store_name", account.get("account_id", "unknown")),
                platform=account.get("platform", "unknown"),
                shop_id=account.get("shop_region"),
                status="active" if account.get("enabled", False) else "inactive"
            ))
        
        # #region agent log
        with open(debug_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'location':'collection.py:list_accounts:result','message':'Result prepared','data':{'count':len(result),'firstResult':{'id':result[0].id,'name':result[0].name,'platform':result[0].platform,'shop_id':result[0].shop_id} if result else None},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H2,H3'})+'\n')
        # #endregion
        
        logger.info(f"返回账号列表: {len(result)} 条记录")
        
        # [*] Phase 3: 写入缓存
        if request and hasattr(request.app.state, 'cache_service'):
            cache_service = request.app.state.cache_service
            await cache_service.set("accounts_list", result, ttl=300, platform=platform)  # 5分钟TTL
        
        return result
    
    except Exception as e:
        logger.error(f"加载账号列表失败: {e}")
        raise HTTPException(status_code=500, detail="加载账号列表失败")


# ============================================================
# 任务 API
# ============================================================

@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    创建采集任务（v4.7.0）
    
    v4.7.0 更新：
    - 支持子域数组（sub_domains）
    - 支持调试模式（debug_mode）
    - 支持任务粒度优化（一账号一任务，循环采集所有域）
    - 支持账号能力过滤（capabilities）
    """
    # 生成任务ID
    task_uuid = str(uuid.uuid4())
    
    # v4.7.0: 获取账号信息并过滤数据域
    from backend.services.task_service import TaskService
    from local_accounts import LOCAL_ACCOUNTS
    
    # 查找账号信息
    account_info = None
    for platform_group, accounts in LOCAL_ACCOUNTS.items():
        for acc in accounts:
            if acc.get('account_id') == request.account_id:
                account_info = acc
                break
        if account_info:
            break
    
    if not account_info:
        raise HTTPException(status_code=404, detail=f"账号 {request.account_id} 不存在")
    
    # 过滤数据域
    task_service = TaskService(db)
    filtered_domains, unsupported_domains = task_service.filter_domains_by_account_capability(
        account_info, request.data_domains
    )
    
    # 如果所有数据域都不支持，返回错误
    if not filtered_domains:
        raise HTTPException(
            status_code=400,
            detail=f"账号 {request.account_id} 不支持任何请求的数据域: {', '.join(unsupported_domains)}"
        )
    
    # 记录被过滤的数据域
    if unsupported_domains:
        logger.warning(
            f"Filtered out unsupported domains for {request.account_id}: {unsupported_domains}"
        )
    
    # v4.7.0: 计算总数据域数量（含子域，仅计算支持的数据域）
    total_domains_count = len(filtered_domains)
    if request.sub_domains:
        # 如果有子域，每个数据域 × 子域数量
        total_domains_count = len(filtered_domains) * len(request.sub_domains)
    
    # 创建任务记录（使用过滤后的数据域）
    task = CollectionTask(
        task_id=task_uuid,
        platform=request.platform,
        account=request.account_id,
        status="pending",
        config_id=request.config_id,
        trigger_type="manual",
        data_domains=filtered_domains,  # v4.7.0: 使用过滤后的数据域
        sub_domains=request.sub_domains,  # v4.7.0: 子域数组
        granularity=request.granularity,
        date_range=request.date_range,
        # v4.7.0: 任务粒度优化字段
        total_domains=total_domains_count,
        completed_domains=[],
        failed_domains=[],
        current_domain=None,
        debug_mode=request.debug_mode,  # v4.7.0: 调试模式
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 记录日志
    log = CollectionTaskLog(
        task_id=task.id,
        level="info",
        message="任务已创建",
        details={
            "trigger": "manual",
            "account": request.account_id,
            "total_domains": total_domains_count,
            "debug_mode": request.debug_mode
        }
    )
    db.add(log)
    await db.commit()
    
    logger.info(f"Created collection task: {task_uuid} ({request.platform}/{request.account_id}) - {total_domains_count} domains, debug_mode={request.debug_mode}")
    
    # v4.7.0 + Phase 9.1: 启动后台采集任务（使用过滤后的数据域）
    asyncio.create_task(
        _execute_collection_task_background(
            task_id=task_uuid,
            platform=request.platform,
            account_id=request.account_id,
            data_domains=filtered_domains,  # v4.7.0: 使用过滤后的数据域
            sub_domains=request.sub_domains,
            date_range=request.date_range,
            granularity=request.granularity,
            debug_mode=request.debug_mode,
            parallel_mode=request.parallel_mode,  # [*] Phase 9.1: 并行执行模式
            max_parallel=request.max_parallel,  # [*] Phase 9.1: 最大并发数
            db_session_maker=db.get_bind()  # 传递数据库引擎
        )
    )
    
    return task


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务列表"""
    stmt = select(CollectionTask)
    
    if platform:
        stmt = stmt.where(CollectionTask.platform == platform)
    
    if status:
        stmt = stmt.where(CollectionTask.status == status)
    
    stmt = stmt.order_by(desc(CollectionTask.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return tasks


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务详情"""
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return task


@router.delete("/tasks/{task_id}", response_model=SuccessResponse[None])
async def cancel_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """取消任务"""
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 只能取消pending或running状态的任务
    if task.status not in ["pending", "queued", "running", "paused"]:
        raise HTTPException(status_code=400, detail=f"无法取消{task.status}状态的任务")
    
    task.status = "cancelled"
    task.error_message = "用户取消"
    
    # 记录日志
    log = CollectionTaskLog(
        task_id=task.id,
        level="info",
        message="任务已取消",
        details={"previous_status": task.status}
    )
    db.add(log)
    await db.commit()
    
    logger.info(f"Cancelled task: {task_id}")
    return {"message": "任务已取消"}


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    重试任务
    
    创建新任务，重新开始整个流程
    """
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    original_task = result.scalar_one_or_none()
    
    if not original_task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 只能重试failed或cancelled状态的任务
    if original_task.status not in ["failed", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"无法重试{original_task.status}状态的任务")
    
    # 创建新任务
    new_task = CollectionTask(
        task_id=str(uuid.uuid4()),
        platform=original_task.platform,
        account=original_task.account,
        status="pending",
        config_id=original_task.config_id,
        trigger_type="retry",
        data_domains=original_task.data_domains,
        sub_domain=original_task.sub_domain,
        granularity=original_task.granularity,
        date_range=original_task.date_range,
        retry_count=original_task.retry_count + 1,
        parent_task_id=original_task.id,
    )
    
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    # 记录日志
    log = CollectionTaskLog(
        task_id=new_task.id,
        level="info",
        message="重试任务已创建",
        details={"original_task_id": task_id}
    )
    db.add(log)
    await db.commit()
    
    logger.info(f"Created retry task: {new_task.task_id} (original: {task_id})")
    return new_task


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    继续任务
    
    从暂停点继续执行（适用于验证码暂停后的恢复）
    """
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 只能继续paused状态的任务
    if task.status != "paused":
        raise HTTPException(status_code=400, detail=f"无法继续{task.status}状态的任务")
    
    # 更新状态为running
    task.status = "running"
    task.verification_type = None  # 清除验证码状态
    
    # 记录日志
    log = CollectionTaskLog(
        task_id=task.id,
        level="info",
        message="任务已恢复",
        details={"previous_status": "paused"}
    )
    db.add(log)
    await db.commit()
    
    logger.info(f"Resumed task: {task_id}")
    
    # TODO: 触发任务执行器继续执行
    
    return task


@router.get("/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: str = Path(..., description="任务ID"),
    level: Optional[str] = Query(None, description="按日志级别筛选"),
    limit: int = Query(100, ge=1, le=500, description="返回数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务日志"""
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    stmt = select(CollectionTaskLog).where(CollectionTaskLog.task_id == task.id)
    
    if level:
        stmt = stmt.where(CollectionTaskLog.level == level)
    
    stmt = stmt.order_by(CollectionTaskLog.timestamp).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return logs


@router.get("/tasks/{task_id}/screenshot")
async def get_task_screenshot(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取任务截图（验证码截图）
    
    返回任务的验证码截图文件（如果存在）
    
    Phase 1.5.6新增功能
    """
    from pathlib import Path as PathLib
    import os
    
    # 查询任务
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查任务是否有screenshot_path
    screenshot_path = task.screenshot_path
    
    if not screenshot_path:
        raise HTTPException(status_code=404, detail="任务没有截图")
    
    # 转换为绝对路径
    if not PathLib(screenshot_path).is_absolute():
        # 如果是相对路径，相对于项目根目录
        project_root = PathLib(__file__).parent.parent.parent
        screenshot_path = str(project_root / screenshot_path)
    
    # 检查文件是否存在
    if not os.path.exists(screenshot_path):
        raise HTTPException(status_code=404, detail=f"截图文件不存在: {screenshot_path}")
    
    # 返回文件
    return FileResponse(
        path=screenshot_path,
        media_type="image/png",
        filename=f"task_{task_id}_screenshot.png"
    )


# ============================================================
# 历史和统计 API
# ============================================================

@router.get("/history", response_model=TaskHistoryResponse)
async def get_history(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集历史记录（分页）"""
    from sqlalchemy import func
    
    # 构建查询条件
    conditions = []
    
    if platform:
        conditions.append(CollectionTask.platform == platform)
    
    if status:
        conditions.append(CollectionTask.status == status)
    
    if start_date:
        conditions.append(CollectionTask.created_at >= datetime.combine(start_date, datetime.min.time()))
    
    if end_date:
        conditions.append(CollectionTask.created_at <= datetime.combine(end_date, datetime.max.time()))
    
    # 统计总数
    count_stmt = select(func.count(CollectionTask.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    # 分页查询
    stmt = select(CollectionTask)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(desc(CollectionTask.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    return TaskHistoryResponse(
        data=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/history/stats", response_model=TaskStatsResponse)
async def get_history_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集统计数据"""
    from backend.schemas.collection import DailyStats
    from sqlalchemy import func
    start_date = datetime.now() - timedelta(days=days)
    
    # 按状态统计
    status_stmt = select(
        CollectionTask.status,
        func.count(CollectionTask.id).label("count")
    ).where(
        CollectionTask.created_at >= start_date
    ).group_by(CollectionTask.status)
    status_result = await db.execute(status_stmt)
    status_stats = status_result.all()
    
    # 按平台统计
    platform_stmt = select(
        CollectionTask.platform,
        func.count(CollectionTask.id).label("count")
    ).where(
        CollectionTask.created_at >= start_date
    ).group_by(CollectionTask.platform)
    platform_result = await db.execute(platform_stmt)
    platform_stats = platform_result.all()
    
    # 按状态统计
    status_dict = {s[0]: s[1] for s in status_stats}
    total = sum(status_dict.values()) or 1
    completed_count = status_dict.get("completed", 0)
    failed_count = status_dict.get("failed", 0)
    running_count = status_dict.get("running", 0)
    queued_count = status_dict.get("queued", 0)
    success_rate = round(completed_count / total * 100, 2)
    
    # 按日统计（简化版，实际可以更详细）
    daily_stats = []
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).date()
        day_stmt = select(CollectionTask).where(
            func.date(CollectionTask.created_at) == day
        )
        day_result = await db.execute(day_stmt)
        day_tasks = day_result.scalars().all()
        
        day_total = len(day_tasks)
        day_completed = sum(1 for t in day_tasks if t.status == "completed")
        day_failed = sum(1 for t in day_tasks if t.status == "failed")
        day_rate = round(day_completed / day_total * 100, 2) if day_total > 0 else 0
        
        daily_stats.append(DailyStats(
            date=day,
            total=day_total,
            completed=day_completed,
            failed=day_failed,
            success_rate=day_rate
        ))
    
    return TaskStatsResponse(
        total_tasks=total,
        completed=completed_count,
        failed=failed_count,
        running=running_count,
        queued=queued_count,
        success_rate=success_rate,
        daily_stats=daily_stats
    )


# ============================================================
# 健康检查
# ============================================================

# ============================================================
# 调度管理 API
# ============================================================

@router.post("/configs/{config_id}/schedule", response_model=ScheduleResponse)
async def update_config_schedule(
    config_id: int,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新配置的定时设置
    
    启用/禁用定时采集，设置Cron表达式
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE
    
    if not APSCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="定时调度服务未安装")
    
    # 获取配置
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    # 验证Cron表达式
    if request.schedule_enabled and request.schedule_cron:
        if not CollectionScheduler.validate_cron_expression(request.schedule_cron):
            raise HTTPException(status_code=400, detail="无效的Cron表达式")
    
    # 更新数据库
    config.schedule_enabled = request.schedule_enabled
    config.schedule_cron = request.schedule_cron if request.schedule_enabled else None
    await db.commit()
    
    # 更新调度器
    try:
        scheduler = CollectionScheduler.get_instance()
        
        if request.schedule_enabled and request.schedule_cron:
            await scheduler.add_schedule(config_id, request.schedule_cron)
            action = "enabled"
        else:
            await scheduler.remove_schedule(config_id)
            action = "disabled"
        
        logger.info(f"Schedule {action} for config {config_id}")
        
        # 获取下次执行时间
        next_run_time = None
        job_id = None
        if request.schedule_enabled:
            job_info = scheduler.get_job_info(config_id)
            if job_info:
                next_run_time = job_info.get("next_run_time")
                job_id = job_info.get("job_id")
        
        return ScheduleResponse(
            message=f"定时任务已{'启用' if request.schedule_enabled else '禁用'}",
            config_id=config_id,
            job_id=job_id,
            next_run_time=next_run_time
        )
        
    except Exception as e:
        logger.error(f"Failed to update schedule for config {config_id}: {e}")
        raise HTTPException(status_code=500, detail=f"更新调度失败: {str(e)}")


@router.get("/configs/{config_id}/schedule", response_model=ScheduleInfoResponse)
async def get_config_schedule(
    config_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取配置的定时状态
    
    返回下次执行时间、历史执行记录等
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE
    
    # 获取配置
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    # 初始值
    next_run_time = None
    job_id = None
    
    # 获取调度器信息
    if APSCHEDULER_AVAILABLE and config.schedule_enabled:
        try:
            scheduler = CollectionScheduler.get_instance()
            job_info = scheduler.get_job_info(config_id)
            if job_info:
                next_run_time = job_info.get("next_run_time")
                job_id = job_info.get("job_id")
        except Exception as e:
            logger.warning(f"Failed to get job info for config {config_id}: {e}")
    
    return ScheduleInfoResponse(
        enabled=config.schedule_enabled,
        cron=config.schedule_cron,
        next_run_time=next_run_time,
        job_id=job_id
    )


@router.post("/schedule/validate", response_model=CronValidationResponse)
async def validate_cron_expression(request: CronValidateRequest):
    """
    验证Cron表达式
    
    返回是否有效及人类可读描述
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE
    
    if not APSCHEDULER_AVAILABLE:
        return CronValidationResponse(
            valid=False,
            error="APScheduler未安装"
        )
    
    is_valid = CollectionScheduler.validate_cron_expression(request.cron_expression)
    
    return CronValidationResponse(
        valid=is_valid,
        error=None if is_valid else "无效的Cron表达式格式",
        description=CollectionScheduler.get_cron_description(request.cron_expression) if is_valid else None
    )


@router.get("/schedule/presets", response_model=CronPresetsResponse)
async def get_cron_presets():
    """
    获取预定义的Cron表达式
    
    返回常用的定时配置选项
    """
    from backend.services.collection_scheduler import CRON_PRESETS, CollectionScheduler
    from backend.schemas.collection import CronPresetItem
    
    presets = []
    for name, cron in CRON_PRESETS.items():
        presets.append(CronPresetItem(
            name=name,
            cron=cron,
            description=CollectionScheduler.get_cron_description(cron)
        ))
    
    return CronPresetsResponse(presets=presets)


@router.get("/schedule/jobs", response_model=ScheduledJobsResponse)
async def list_scheduled_jobs():
    """
    获取所有定时任务
    
    返回当前所有已注册的定时任务
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE
    from backend.schemas.collection import ScheduledJobInfo
    
    if not APSCHEDULER_AVAILABLE:
        return ScheduledJobsResponse(
            jobs=[],
            total=0,
            error="调度服务未安装"
        )
    
    try:
        scheduler = CollectionScheduler.get_instance()
        jobs_data = scheduler.get_all_jobs()
        
        jobs = [
            ScheduledJobInfo(
                job_id=j.get("job_id"),
                name=j.get("name"),
                next_run_time=j.get("next_run_time"),
                trigger=j.get("trigger", "cron")
            )
            for j in jobs_data
        ]
        
        return ScheduledJobsResponse(
            jobs=jobs,
            total=len(jobs)
        )
    except Exception as e:
        logger.error(f"Failed to list scheduled jobs: {e}")
        return ScheduledJobsResponse(
            jobs=[],
            total=0,
            error=str(e)
        )


# ============================================================
# 健康检查
# ============================================================

@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """
    采集模块健康检查
    
    返回：
    - 运行中任务数
    - 排队任务数
    - 浏览器池状态
    - 数据库状态
    - 调度器状态
    """
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE
    from backend.schemas.collection import BrowserPoolStatus
    
    # 尝试查询任务统计（如果表结构不存在则返回0）
    running_count = 0
    queued_count = 0
    try:
        from sqlalchemy import text
        # 使用原生SQL查询，避免ORM模型与数据库不同步的问题
        result = await db.execute(text("""
            SELECT status, COUNT(*) as count 
            FROM collection_tasks 
            WHERE status IN ('running', 'queued')
            GROUP BY status
        """))
        for row in result:
            if row[0] == "running":
                running_count = row[1]
            elif row[0] == "queued":
                queued_count = row[1]
    except Exception as e:
        # 表不存在或结构不对，返回默认值
        logger.warning(f"Health check task query failed (migration pending?): {e}")
    
    # 浏览器池状态（简化版）
    from backend.services.task_service import TaskService
    max_concurrent = TaskService.MAX_CONCURRENT_TASKS
    
    # 数据库状态
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    
    # 调度器状态
    scheduler_status = "not_installed" if not APSCHEDULER_AVAILABLE else "ok"
    if APSCHEDULER_AVAILABLE:
        try:
            from backend.services.collection_scheduler import CollectionScheduler
            scheduler = CollectionScheduler.get_instance()
            if not scheduler:
                scheduler_status = "error"
        except Exception:
            scheduler_status = "error"
    
    return HealthCheckResponse(
        status="healthy",
        running_tasks=running_count,
        queued_tasks=queued_count,
        browser_pool=BrowserPoolStatus(
            active=running_count,
            max_allowed=max_concurrent
        ),
        database=db_status,
        scheduler=scheduler_status
    )


# ============================================================
# 后台任务执行（v4.7.0）
# ============================================================

async def _execute_collection_task_background(
    task_id: str,
    platform: str,
    account_id: str,
    data_domains: List[str],
    sub_domains: Optional[List[str]],
    date_range: Dict[str, str],
    granularity: str,
    debug_mode: bool,
    parallel_mode: bool,  # [*] Phase 9.1
    max_parallel: int,  # [*] Phase 9.1
    db_session_maker
):
    """
    后台执行采集任务（v4.7.0 + Phase 9.1）
    
    Args:
        task_id: 任务ID
        platform: 平台
        account_id: 账号ID
        data_domains: 数据域列表
        sub_domains: 子域列表
        date_range: 日期范围
        granularity: 粒度
        debug_mode: 调试模式
        parallel_mode: [*] 并行执行模式（Phase 9.1）
        max_parallel: [*] 最大并发数（Phase 9.1）
        db_session_maker: 数据库引擎（用于创建新session）
    """
    from backend.models.database import AsyncSessionLocal
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
    import importlib.util
    
    # 创建新的异步数据库session（后台任务需要独立session）
    async with AsyncSessionLocal() as db:
        try:
            # 更新任务状态为running
            result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Task {task_id} not found in database")
                return
            
            task.status = "running"
            task.started_at = datetime.utcnow()
            await db.commit()
            
            # 加载账号信息（v4.7.0: 从数据库加载）
            try:
                from backend.services.account_loader_service import get_account_loader_service
                
                account_loader = get_account_loader_service()
                # [*] v4.18.2修复：使用异步方法加载账号
                account = await account_loader.load_account_async(account_id, db)
                
                if not account:
                    raise ValueError(f"Account {account_id} not found or disabled")
            
            except Exception as e:
                logger.error(f"Failed to load account {account_id}: {e}")
                task.status = "failed"
                task.error_message = f"账号加载失败: {str(e)}"
                task.completed_at = datetime.utcnow()
                await db.commit()
                # v4.7.4: 失败状态通过 HTTP 轮询获取
                return
            
            # 创建执行器
            executor = CollectionExecutorV2()
            
            # 执行采集
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # 根据debug_mode和环境配置启动浏览器
                from modules.apps.collection_center.browser_config_helper import get_browser_launch_args, get_browser_context_args
                
                browser = await p.chromium.launch(**get_browser_launch_args(debug_mode=debug_mode))
                context = await browser.new_context(**get_browser_context_args())
                page = await context.new_page()
                
                try:
                    # [*] Phase 9.1: 根据parallel_mode选择执行方式
                    if parallel_mode:
                        # 并行执行模式（每个域独立浏览器上下文）
                        logger.info(f"Task {task_id}: Using PARALLEL execution mode (max_parallel={max_parallel})")
                        result = await executor.execute_parallel_domains(
                            task_id=task_id,
                            platform=platform,
                            account_id=account_id,
                            account=account,
                            data_domains=data_domains,
                            date_range=date_range,
                            granularity=granularity,
                            browser=browser,
                            max_parallel=max_parallel,
                            debug_mode=debug_mode,
                        )
                    else:
                        # 顺序执行模式（传统方式）
                        result = await executor.execute(
                            task_id=task_id,
                            platform=platform,
                            account_id=account_id,
                            account=account,
                            data_domains=data_domains,
                            sub_domains=sub_domains,
                            date_range=date_range,
                            granularity=granularity,
                            page=page,
                            debug_mode=debug_mode,
                        )
                    
                    # 更新任务状态
                    task.status = result.status
                    task.progress = 100 if result.status in ["completed", "partial_success"] else 0
                    task.files_collected = result.files_collected
                    task.error_message = result.error_message
                    task.completed_at = datetime.utcnow()
                    task.duration_seconds = result.duration_seconds
                    
                    # v4.7.0: 更新域级别字段
                    task.completed_domains = result.completed_domains
                    task.failed_domains = result.failed_domains
                    
                    await db.commit()
                    
                    logger.info(f"Task {task_id} completed: {result.status}, files={result.files_collected}")
                    
                finally:
                    await page.close()
                    await context.close()
                    await browser.close()
        
        except Exception as e:
            logger.exception(f"Background task {task_id} failed: {e}")
            
            # 更新任务状态为失败
            try:
                result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    await db.commit()
                    # v4.7.4: 失败状态通过 HTTP 轮询获取
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")
