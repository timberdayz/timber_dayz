"""
系统资源监控API

v4.19.0新增：执行器统一管理和资源优化
- 资源使用情况监控
- 执行器统计信息
- 数据库连接池统计

注意：所有接口需要管理员权限
"""

from fastapi import APIRouter, Depends, HTTPException, status
import psutil
import threading
from typing import Dict, Any

from backend.services.executor_manager import get_executor_manager
from backend.models.database import engine, async_engine
from backend.routers.auth import get_current_user

router = APIRouter(prefix="/system", tags=["系统监控"])


@router.get("/resource-usage")
async def get_resource_usage(
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取当前资源使用情况（需要管理员权限）
    
    Returns:
        Dict[str, Any]: 资源使用情况
        - cpu_usage: CPU使用率（%）
        - memory_usage: 内存使用率（%）
        - process_count: 进程数
        - thread_count: 线程数
    """
    # [WARN] 仅管理员可访问，避免信息泄露
    # [*] 注意：current_user 是 DimUser 对象，需要检查 role 属性
    if not hasattr(current_user, 'role') or getattr(current_user, 'role', None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    return {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "memory_usage": psutil.virtual_memory().percent,
        "process_count": len(psutil.pids()),
        "thread_count": threading.active_count()
    }


@router.get("/executor-stats")
async def get_executor_stats(
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取执行器统计信息（需要管理员权限）
    
    Returns:
        Dict[str, Any]: 执行器统计信息
        - cpu_executor: 进程池信息
            - max_workers: 最大worker数
            - active_tasks: 活跃任务数（N/A，无法直接获取）
        - io_executor: 线程池信息
            - max_workers: 最大worker数
            - active_tasks: 活跃任务数（N/A，无法直接获取）
    """
    # [WARN] 仅管理员可访问
    # [*] 注意：current_user 是 DimUser 对象，需要检查 role 属性
    if not hasattr(current_user, 'role') or getattr(current_user, 'role', None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    executor_manager = get_executor_manager()
    
    # [*] 注意：ProcessPoolExecutor和ThreadPoolExecutor没有公开API获取活跃任务数
    # 可以通过跟踪提交的Future对象来估算（P2可选功能）
    return {
        "cpu_executor": {
            "max_workers": executor_manager.cpu_max_workers,  # [*] 使用公开属性，避免访问私有属性
            "active_tasks": "N/A"  # [WARN] 无法直接获取，需要额外实现（P2可选）
        },
        "io_executor": {
            "max_workers": executor_manager.io_max_workers,  # [*] 使用公开属性，避免访问私有属性
            "active_tasks": "N/A"  # [WARN] 无法直接获取，需要额外实现（P2可选）
        }
    }


@router.get("/db-pool-stats")
async def get_db_pool_stats(
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取数据库连接池统计信息（需要管理员权限）
    
    Returns:
        Dict[str, Any]: 连接池统计信息
        - sync_pool: 同步连接池信息
            - size: 连接池大小
            - checked_out: 已检出连接数
            - overflow: 溢出连接数
        - async_pool: 异步连接池信息
            - size: 连接池大小
            - checked_out: 已检出连接数
            - overflow: 溢出连接数
    """
    # [WARN] 仅管理员可访问
    # [*] 注意：current_user 是 DimUser 对象，需要检查 role 属性
    if not hasattr(current_user, 'role') or getattr(current_user, 'role', None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    result = {
        "sync_pool": {},
        "async_pool": {}
    }
    
    # 同步连接池统计
    try:
        pool = engine.pool
        result["sync_pool"] = {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow()
        }
    except Exception as e:
        result["sync_pool"] = {"error": str(e)}
    
    # 异步连接池统计
    try:
        async_pool = async_engine.pool
        result["async_pool"] = {
            "size": async_pool.size(),
            "checked_out": async_pool.checkedout(),
            "overflow": async_pool.overflow()
        }
    except Exception as e:
        result["async_pool"] = {"error": str(e)}
    
    return result

