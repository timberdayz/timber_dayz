"""
系统资源监控 API

提供受管理员保护的资源、执行器和数据库连接池观测接口。
"""

from typing import Any, Dict
import threading

import psutil
from fastapi import APIRouter, Depends

from backend.dependencies.auth import require_admin
from backend.models.database import async_engine, engine
from backend.services.executor_manager import get_executor_manager

router = APIRouter(prefix="/system", tags=["系统监控"])


@router.get("/resource-usage")
async def get_resource_usage(
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    """
    获取当前资源使用情况。
    """
    return {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "memory_usage": psutil.virtual_memory().percent,
        "process_count": len(psutil.pids()),
        "thread_count": threading.active_count(),
    }


@router.get("/executor-stats")
async def get_executor_stats(
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    """
    获取执行器统计信息。
    """
    executor_manager = get_executor_manager()
    return {
        "cpu_executor": {
            "max_workers": executor_manager.cpu_max_workers,
            "active_tasks": "N/A",
        },
        "io_executor": {
            "max_workers": executor_manager.io_max_workers,
            "active_tasks": "N/A",
        },
    }


@router.get("/db-pool-stats")
async def get_db_pool_stats(
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    """
    获取数据库连接池统计信息。
    """
    result: Dict[str, Any] = {
        "sync_pool": {},
        "async_pool": {},
    }

    try:
        pool = engine.pool
        result["sync_pool"] = {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as exc:
        result["sync_pool"] = {"error": str(exc)}

    try:
        pool = async_engine.pool
        result["async_pool"] = {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as exc:
        result["async_pool"] = {"error": str(exc)}

    return result
