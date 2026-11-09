from typing import Any, Dict
import threading

import psutil
from fastapi import APIRouter, Depends

from backend.dependencies.auth import require_admin
from backend.models.database import engine, get_async_engine
from backend.services.executor_manager import get_executor_manager

router = APIRouter(prefix="/system", tags=["系统监控"])


def _describe_pool(pool: Any) -> Dict[str, Any]:
    """描述连接池状态（对没有池统计方法的池类安全）。

    [*] 2026-11-09：async 引擎改为**按事件循环分发**，每个事件循环有自己的
    连接池；这里要看的是**当前请求所在循环**的池，而不是全局那个。
    """

    def _num(method_name: str) -> int:
        getter = getattr(pool, method_name, None)
        if not callable(getter):
            return 0
        try:
            return int(getter())
        except Exception:  # noqa: BLE001 - 监控接口不能因为统计失败而 500
            return 0

    status = ""
    status_getter = getattr(pool, "status", None)
    if callable(status_getter):
        try:
            status = str(status_getter())
        except Exception:  # noqa: BLE001
            status = ""

    return {
        "type": type(pool).__name__,
        "size": _num("size"),
        "checked_out": _num("checkedout"),
        "overflow": _num("overflow"),
        "status": status,
    }


@router.get("/resource-usage")
async def get_resource_usage(current_user=Depends(require_admin)) -> Dict[str, Any]:
    return {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "memory_usage": psutil.virtual_memory().percent,
        "process_count": len(psutil.pids()),
        "thread_count": threading.active_count(),
    }


@router.get("/executor-stats")
async def get_executor_stats(current_user=Depends(require_admin)) -> Dict[str, Any]:
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
async def get_db_pool_stats(current_user=Depends(require_admin)) -> Dict[str, Any]:
    result: Dict[str, Any] = {"sync_pool": {}, "async_pool": {}}

    try:
        pool = engine.pool
        result["sync_pool"] = _describe_pool(pool)
    except Exception as exc:
        result["sync_pool"] = {"error": str(exc)}

    try:
        pool = get_async_engine().pool
        result["async_pool"] = _describe_pool(pool)
    except Exception as exc:
        result["async_pool"] = {"error": str(exc)}

    return result
